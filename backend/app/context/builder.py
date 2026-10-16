import calendar
import re
import unicodedata
from datetime import date, datetime
from statistics import mean

from app.models import Checkin, Lek, Patient, PatientContext

CHEMO_WINDOW_DAYS = 42
RECENT_CHECKINS = 10

REGIMEN_EXPANSIONS: dict[str, list[str]] = {
    "r-chop": ["rituximab", "cyklofosfamid", "doxorubicin", "vinkristin", "prednison"],
    "chop": ["cyklofosfamid", "doxorubicin", "vinkristin", "prednison"],
    "mfolfox6": ["5-fu", "leukovorin", "oxaliplatina"],
    "folfox": ["5-fu", "leukovorin", "oxaliplatina"],
    "folfiri": ["5-fu", "leukovorin", "irinotekan"],
    "folfirinox": ["5-fu", "leukovorin", "irinotekan", "oxaliplatina"],
    "capox": ["kapecitabin", "oxaliplatina"],
    "xelox": ["kapecitabin", "oxaliplatina"],
    "ac": ["doxorubicin", "cyklofosfamid"],
    "ec": ["epirubicin", "cyklofosfamid"],
    "tc": ["docetaxel", "cyklofosfamid"],
    "abvd": ["doxorubicin", "bleomycin", "vinblastin", "dakarbazin"],
    "beacopp": ["bleomycin", "etoposid", "doxorubicin", "cyklofosfamid", "vinkristin", "prokarbazin", "prednison"],
    "bep": ["bleomycin", "etoposid", "cisplatina"],
    "gemcis": ["gemcitabin", "cisplatina"],
}

# Stem (folded, diacritics-free) -> drug classes.
DRUG_CLASSES: dict[str, list[str]] = {
    "doxorubicin": ["cytotoxic", "cardiotoxic"],
    "epirubicin": ["cytotoxic", "cardiotoxic"],
    "cyklofosfamid": ["cytotoxic"], "cyclophosphamid": ["cytotoxic"],
    "oxaliplatin": ["cytotoxic", "platinum", "neurotoxic"],
    "cisplatin": ["cytotoxic", "platinum"],
    "karboplatin": ["cytotoxic", "platinum"], "carboplatin": ["cytotoxic", "platinum"],
    "5-fu": ["cytotoxic", "fluoropyrimidine"], "fluorouracil": ["cytotoxic", "fluoropyrimidine"],
    "kapecitabin": ["cytotoxic", "fluoropyrimidine"], "capecitabin": ["cytotoxic", "fluoropyrimidine"],
    "irinotekan": ["cytotoxic", "irinotecan"], "irinotecan": ["cytotoxic", "irinotecan"],
    "etoposid": ["cytotoxic"],
    "vinkristin": ["cytotoxic", "neurotoxic"], "vincristin": ["cytotoxic", "neurotoxic"],
    "paklitaxel": ["cytotoxic", "neurotoxic"], "paclitaxel": ["cytotoxic", "neurotoxic"],
    "docetaxel": ["cytotoxic", "neurotoxic"],
    "gemcitabin": ["cytotoxic"], "pemetrexed": ["cytotoxic"], "bleomycin": ["cytotoxic"],
    "vinblastin": ["cytotoxic", "neurotoxic"], "vinorelbin": ["cytotoxic"], "dakarbazin": ["cytotoxic"],
    "temozolomid": ["cytotoxic"], "prokarbazin": ["cytotoxic"],
    "ipilimumab": ["immunotherapy"], "nivolumab": ["immunotherapy"], "atezolizumab": ["immunotherapy"],
    "pembrolizumab": ["immunotherapy"], "durvalumab": ["immunotherapy"], "avelumab": ["immunotherapy"],
    "cemiplimab": ["immunotherapy"], "dostarlimab": ["immunotherapy"],
    "warfarin": ["anticoagulant"], "enoxaparin": ["anticoagulant"], "nadroparin": ["anticoagulant"],
    "apixaban": ["anticoagulant"], "rivaroxaban": ["anticoagulant"], "dabigatran": ["anticoagulant"],
    "edoxaban": ["anticoagulant"], "dalteparin": ["anticoagulant"],
    "sunitinib": ["antiangiogenic"], "bevacizumab": ["antiangiogenic"], "pazopanib": ["antiangiogenic"],
    "cabozantinib": ["antiangiogenic"], "lenvatinib": ["antiangiogenic"], "sorafenib": ["antiangiogenic"],
    "axitinib": ["antiangiogenic"], "regorafenib": ["antiangiogenic"], "ramucirumab": ["antiangiogenic"],
    "aflibercept": ["antiangiogenic"],
    "trastuzumab": ["cardiotoxic"], "pertuzumab": ["cardiotoxic"],
    "dexametazon": ["corticosteroid"], "dexamethason": ["corticosteroid"], "prednison": ["corticosteroid"],
    "metylprednisolon": ["corticosteroid"], "hydrokortison": ["corticosteroid"],
    "morfin": ["opioid"], "oramorph": ["opioid"], "oxykodon": ["opioid"], "fentanyl": ["opioid"],
    "hydromorfon": ["opioid"], "tramadol": ["opioid"], "buprenorfin": ["opioid"], "tapentadol": ["opioid"],
    "inzulin": ["insulin"], "insulin": ["insulin"],
    "metformin": ["metformin"],
    "letrozol": ["aromatase_inhibitor"], "anastrozol": ["aromatase_inhibitor"], "exemestan": ["aromatase_inhibitor"],
}

ORAL_CYTOTOXICS = ("kapecitabin", "capecitabin", "temozolomid")

_STATED_END = re.compile(r"ukoncen\w*\s+(\d{1,2})\s*/\s*(\d{4})")


def fold(text: str) -> str:
    """Lower-case and strip diacritics, keeping one output char per input char (indices stay valid)."""
    out = []
    for char in text:
        base = unicodedata.normalize("NFKD", char)
        kept = "".join(part for part in base if not unicodedata.combining(part)) or char
        out.append(kept[0].lower())
    return "".join(out)


def _expand(text: str) -> str:
    folded = fold(text)
    extra = []
    for acronym, drugs in REGIMEN_EXPANSIONS.items():
        if re.search(rf"(?<![\w-]){re.escape(acronym)}(?![\w])", folded):
            extra += drugs
    return folded + " " + " ".join(extra)


def classes_in(text: str) -> set[str]:
    expanded = _expand(text)
    found: set[str] = set()
    for stem, classes in DRUG_CLASSES.items():
        if stem in expanded:
            found.update(classes)
    return found


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def active_meds(patient: Patient, day: date) -> list[Lek]:
    meds = []
    for med in patient.leky:
        start, end = _parse_date(med.od_data), _parse_date(med.do_data)
        if start and start > day:
            continue
        if end and end < day:
            continue
        meds.append(med)
    return meds


def _treatment_text(patient: Patient, meds: list[Lek]) -> str:
    return " | ".join([patient.lecba.rezim, *patient.lecba.leky, *(f"{med.lek} {med.indikace}" for med in meds)])


def _last_cytotoxic_day(patient: Patient, day: date) -> date | None:
    regimen_cytotoxic = "cytotoxic" in classes_in(" ".join([patient.lecba.rezim, *patient.lecba.leky]))
    candidates: list[date] = []
    if regimen_cytotoxic:
        started = [cycle.datum_d1 for cycle in patient.lecba.cykly if cycle.datum_d1 <= day]
        candidates += started
        if not patient.lecba.cykly and "ukoncen" not in fold(patient.lecba.rezim):
            candidates.append(day)
    for med in patient.leky:
        if any(stem in fold(med.lek) for stem in ORAL_CYTOTOXICS):
            start, end = _parse_date(med.od_data), _parse_date(med.do_data)
            if start and start > day:
                continue
            candidates.append(min(end, day) if end else day)
    stated = _STATED_END.search(fold(f"{patient.lecba.rezim} {patient.lecba.poznamka}"))
    if stated:
        month, year = int(stated.group(1)), int(stated.group(2))
        if 1 <= month <= 12:
            end = date(year, month, calendar.monthrange(year, month)[1])
            if end <= day:
                candidates.append(end)
    return max(candidates) if candidates else None


def _baselines(patient: Patient, earlier: list[Checkin]) -> dict[str, float]:
    first_week = [checkin for checkin in earlier if checkin.den_sledovani <= 7 and checkin.vitalni_funkce]
    keys = {"bp_sys": "tk_sys", "bp_dia": "tk_dia", "pulse": "tepova_frekvence", "spo2": "spo2"}
    baselines: dict[str, float] = {}
    for name, key in keys.items():
        values = [checkin.vitalni_funkce[key].hodnota for checkin in first_week if key in checkin.vitalni_funkce]
        if values:
            baselines[name] = round(mean(values), 1)
    weights = [checkin.vitalni_funkce["vaha_kg"].hodnota for checkin in earlier if checkin.vitalni_funkce and "vaha_kg" in checkin.vitalni_funkce]
    baselines["weight"] = weights[0] if weights else patient.antropometrie.vaha_kg_vychozi
    baselines["ecog"] = float(patient.ecog_vychozi)
    for checkin in earlier:
        for fill in checkin.dotazniky:
            for answer in fill.odpovedi:
                if answer.otazka_id == "sobestacnost" and isinstance(answer.odpoved_index, int):
                    baselines.setdefault("sobestacnost", float(answer.odpoved_index))
    return baselines


def build_context(patient: Patient, as_of: datetime, extra_checkins: list[Checkin] = []) -> PatientContext:
    """Snapshot of what was known at `as_of`: nothing dated later, exams only from earlier days."""
    day = as_of.date()
    checkins = {checkin.checkin_id: checkin for checkin in [*patient.checkiny, *extra_checkins]}
    earlier = sorted((checkin for checkin in checkins.values() if checkin.timestamp <= as_of), key=lambda checkin: checkin.timestamp)
    meds = active_meds(patient, day)
    drug_classes = classes_in(_treatment_text(patient, meds))

    cycle = cycle_day = None
    started = [item for item in patient.lecba.cykly if item.datum_d1 <= day]
    if started:
        current = max(started, key=lambda item: item.datum_d1)
        cycle, cycle_day = current.cyklus, (day - current.datum_d1).days + 1
    last_cytotoxic = _last_cytotoxic_day(patient, day)
    chemo_window = last_cytotoxic is not None and (day - last_cytotoxic).days <= CHEMO_WINDOW_DAYS
    if chemo_window and "cytotoxic" not in drug_classes:
        drug_classes.add("cytotoxic")
    in_nadir = chemo_window and cycle_day is not None and 7 <= cycle_day <= 14 and bool(patient.lecba.delka_cyklu and patient.lecba.delka_cyklu >= 14)

    return PatientContext(
        patient_id=patient.patient_id,
        as_of=as_of,
        age=patient.demografie.vek,
        sex=patient.demografie.pohlavi,
        lang=patient.demografie.jazyk,
        filled_by_default=patient.demografie.vyplnuje,
        diagnosis=patient.diagnoza.diagnoza,
        regimen=patient.lecba.rezim,
        intent=patient.lecba.zamer,
        cycle=cycle,
        cycle_day=cycle_day,
        in_nadir=in_nadir,
        chemo_window=chemo_window,
        drug_classes=sorted(drug_classes),
        meds=meds,
        comorbidities=patient.komorbidity,
        allergies=patient.alergie,
        advance_directive=patient.predem_vyslovena_prani,
        labs=[lab for lab in patient.laboratore if lab.timestamp <= as_of],
        exams=[exam for exam in patient.vysetreni if exam.datum < day],
        team_events=[event for event in patient.udalosti_tymu if event.timestamp <= as_of],
        recent_checkins=earlier[-RECENT_CHECKINS:],
        baselines=_baselines(patient, earlier),
    )
