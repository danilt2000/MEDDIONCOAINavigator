"""Deterministic triage (spec §8): hard rules → context → trends → gaps → contradictions; level = maximum.

The LLM only contributes extracted facts (via NluResult); it never sets or lowers the level."""
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path

import yaml

from app.adapters.meddi_json import without_institution
from app.context.builder import fold
from app.models import Answer, Checkin, Evidence, Fact, NluResult, PatientContext, TriageOutput
from app.nlu.lexicon_cs_sk import MARKED_DROWSINESS
from app.triage.router import route

ENGINE_VERSION = "engine 0.1.0"
NE = "nezadouci_ucinky"
PSYCHO = "psychoonkologicky_screening"
PAIN = "bolest_analgeticka_terapie"
ESAS = "esas"
SYMPTOM_LABELS = {
    "nechutenstvi": "nechutenství", "nevolnost": "nevolnost", "zvraceni": "zvracení", "prujem": "průjem", "zacpa": "zácpa",
    "afty": "afty / bolest při polykání", "bol_hlava": "bolest hlavy", "bol_bricho": "bolest břicha", "bol_klouby": "bolest kloubů",
    "brneni": "brnění", "teplota": "zvýšená teplota", "kuze": "kožní potíže", "unava": "únava", "krvaceni": "krvácení",
    "moceni": "potíže s močením", "dusnost": "zadýchávání",
}
STOP_WORDS = re.compile(r"vynechan|prerusen|vysazen|ukoncen|zastaven|odlozen")


@cache
def rules() -> dict[str, dict]:
    data = yaml.safe_load((Path(__file__).with_name("rules.yaml")).read_text(encoding="utf-8"))
    return {rule["id"]: rule for rule in data["rules"]}


@cache
def version() -> str:
    data = yaml.safe_load((Path(__file__).with_name("rules.yaml")).read_text(encoding="utf-8"))
    return f"{ENGINE_VERSION}, {data['version']}"


@dataclass
class Hit:
    rule: str
    level: int
    finding: str
    evidence: list[Evidence] = field(default_factory=list)
    from_text: bool = False


class Signals:
    """Everything one check-in (or chat message) says, keyed for the rules."""

    def __init__(self, checkin: Checkin, nlu: NluResult):
        self.checkin = checkin
        self.answers: dict[str, Answer] = {}
        for fill in checkin.dotazniky:
            for answer in fill.odpovedi:
                self.answers[f"{fill.dotaznik_id}.{answer.otazka_id}"] = answer
        self.vitals = {key: item.hodnota for key, item in (checkin.vitalni_funkce or {}).items()}
        self.vital_sources = {key: item.zdroj for key, item in (checkin.vitalni_funkce or {}).items()}
        self.facts: dict[str, list[Fact]] = defaultdict(list)
        for fact in nlu.facts:
            self.facts[fact.type].append(fact)

    def answer(self, qid: str, form: str = NE) -> Answer | None:
        return self.answers.get(f"{form}.{qid}")

    def idx(self, qid: str, form: str = NE) -> int | None:
        answer = self.answer(qid, form)
        return answer.odpoved_index if answer and isinstance(answer.odpoved_index, int) else None

    def scale(self, qid: str, form: str) -> float | None:
        answer = self.answer(qid, form)
        if answer is None:
            return None
        if isinstance(answer.odpoved, (int, float)) and not isinstance(answer.odpoved, bool):
            return float(answer.odpoved)
        try:
            return float(str(answer.odpoved).strip())
        except (TypeError, ValueError):
            return None

    def yes(self, qid: str, form: str) -> bool:
        return self.idx(qid, form) == 0

    def has(self, fact_type: str) -> bool:
        return bool(self.facts.get(fact_type))

    def lexicon_confirmed(self, fact_type: str) -> bool:
        """The deterministic lexicon finds the same fact type in the quote (i.e. not an LLM-only reading)."""
        return any(fact_type in _lexicon_types(fact.quote, self.checkin.vyplnil) for fact in self.facts.get(fact_type, []))

    def values(self, fact_type: str) -> list[float]:
        return [float(fact.value) for fact in self.facts.get(fact_type, []) if isinstance(fact.value, (int, float)) and not isinstance(fact.value, bool)]

    def ev_answer(self, qid: str, form: str = NE) -> list[Evidence]:
        answer = self.answer(qid, form)
        if answer is None:
            return []
        return [Evidence(zdroj="dotaznik", citace=f"{answer.otazka} – {answer.odpoved}", checkin_id=self.checkin.checkin_id, datum=str(self.checkin.datum))]

    def ev_vital(self, key: str) -> list[Evidence]:
        if key not in self.vitals:
            return []
        return [Evidence(zdroj="vitalni_funkce", citace=f"{key} {self.vitals[key]:g} ({self.vital_sources.get(key, '')})", checkin_id=self.checkin.checkin_id, datum=str(self.checkin.datum))]

    def ev_fact(self, *fact_types: str) -> list[Evidence]:
        evidence = []
        for fact_type in fact_types:
            for fact in self.facts.get(fact_type, [])[:2]:
                evidence.append(Evidence(zdroj=fact.source, citace=fact.quote, checkin_id=self.checkin.checkin_id, datum=str(self.checkin.datum)))
        return evidence

    # --- derived signals -------------------------------------------------------------------------------------
    def max_temp(self) -> float | None:
        temps = self.values("temperature_c") + ([self.vitals["teplota_c"]] if "teplota_c" in self.vitals else [])
        return max(temps) if temps else None

    def diarrhea_present(self) -> bool:
        return self.idx("prujem") is not None or self.has("diarrhea") or self.has("stool_count_above_normal")

    def diarrhea_grade_form(self) -> int:
        index = self.idx("prujem")
        return 0 if index is None else (1 if index == 0 else 2 if index == 1 else 3)

    def diarrhea_grade_text(self) -> int:
        counts = self.values("stool_count_above_normal")
        if counts:
            top = max(counts)
            return 3 if top >= 7 else 2 if top >= 4 else 1
        return 1 if self.has("diarrhea") else 0

    def diarrhea_grade(self) -> int:
        return max(self.diarrhea_grade_form(), self.diarrhea_grade_text())

    def vomit_present(self) -> bool:
        return self.idx("zvraceni") is not None or self.has("vomiting_episodes_24h") or self.has("vomiting")

    def vomit_grade_form(self) -> int:
        index = self.idx("zvraceni")
        return 0 if index is None else (1 if index == 0 else 2 if index == 1 else 3)

    def vomit_grade_text(self) -> int:
        counts = self.values("vomiting_episodes_24h")
        if not counts:
            return 0
        top = max(counts)
        return 3 if top > 5 else 2 if top >= 3 else 1

    def vomit_grade(self) -> int:
        return max(self.vomit_grade_form(), self.vomit_grade_text())

    def severe_intake_failure(self) -> bool:
        return ((self.idx("nevolnost") or 0) >= 2 or self.idx("nechutenstvi") == 3 or self.idx("afty") == 3
                or self.has("cannot_keep_fluids"))

    def reduced_intake(self) -> bool:
        return (self.severe_intake_failure() or (self.idx("nevolnost") or 0) >= 1 or (self.idx("nechutenstvi") or 0) >= 1
                or (self.idx("afty") or 0) >= 1 or any(self.has(name) for name in ("reduced_intake", "low_fluid_intake", "liquids_only")))

    def intake_score(self) -> int:
        return max(self.idx("nechutenstvi") or 0, self.idx("nevolnost") or 0, self.idx("afty") or 0)

    def dehydration_signs(self) -> list[str]:
        signs = []
        if self.has("oliguria"):
            signs.append("málo močí")
        if self.has("dizziness_standing"):
            signs.append("závrať")
        if self.vitals.get("tepova_frekvence", 0) >= 100:
            signs.append(f"tachykardie {self.vitals['tepova_frekvence']:g}/min")
        if 0 < self.vitals.get("tk_sys", 999) < 100:
            signs.append(f"TK {self.vitals['tk_sys']:g}/{self.vitals.get('tk_dia', 0):g}")
        if self.has("low_fluid_intake"):
            signs.append("příjem tekutin < 1 l")
        return signs

    def abdominal_pain(self) -> bool:
        return self.idx("bol_bricho") is not None or self.has("abdominal_pain_nrs") or self.has("colicky_pain")


@cache
def _lexicon_types(quote: str, author: str) -> frozenset[str]:
    from app.nlu.lexicon_cs_sk import lexicon_facts
    return frozenset(fact.type for fact in lexicon_facts(quote, "zprava", author)[0])


def _num(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _stopped(ctx: PatientContext, stems: tuple[str, ...]) -> bool:
    """A team event says the drug (class) was stopped, interrupted or omitted."""
    for event in ctx.team_events:
        text = fold(event.text)
        if STOP_WORDS.search(text) and any(stem in text for stem in stems):
            return True
    return False


IO_STEMS = ("imunoterapi", "ipilimumab", "nivolumab", "atezolizumab", "pembrolizumab", "durvalumab")
NEUROTOXIC_STEMS = ("oxaliplatin", "vinkristin", "paklitaxel", "paclitaxel", "docetaxel", "vinblastin")
CARDIOTOXIC_STEMS = ("trastuzumab", "doxorubicin", "epirubicin", "pertuzumab")


def _previous(checkin: Checkin, ctx: PatientContext) -> list[Checkin]:
    return [item for item in ctx.recent_checkins if item.checkin_id != checkin.checkin_id and item.timestamp <= checkin.timestamp]


def _signals_of(checkin: Checkin, ctx: PatientContext) -> Signals:
    from app.nlu import analyze
    return Signals(checkin, analyze(checkin, ctx, use_llm=False))


def evaluate(s: Signals, ctx: PatientContext, previous: list[Checkin]) -> list[Hit]:
    hits: list[Hit] = []
    classes = set(ctx.drug_classes)
    io = "immunotherapy" in classes
    io_active = io and not _stopped(ctx, IO_STEMS)
    risky_diarrhea = io or "fluoropyrimidine" in classes or "irinotecan" in classes
    anticoag = "anticoagulant" in classes
    antiangio = "antiangiogenic" in classes
    opioid = "opioid" in classes
    diabetic = any("diabet" in fold(item) for item in ctx.comorbidities) or "insulin" in classes or "metformin" in classes
    copd = any(re.search(r"chopn|copd|astm", fold(item)) for item in ctx.comorbidities)
    filled = [item for item in previous if item.stav == "vyplneno"]

    def hit(rule: str, level: int, finding: str, evidence: list[Evidence], from_text: bool = False):
        hits.append(Hit(rule, level, finding, evidence, from_text))

    # --- fever ------------------------------------------------------------------------------------------------
    temp = s.max_temp()
    teplota = s.idx("teplota")
    chills = s.has("chills")
    fever_evidence = s.ev_vital("teplota_c") + s.ev_answer("teplota") + s.ev_fact("temperature_c", "chills")
    temp_text = "teplota " + (f"{_num(temp)} °C" if temp else "38–39 °C (dotazník)")
    if temp is None and s.has("fever_reported") and teplota != 0:
        temp = 38.0
        temp_text = "pacient udává horečku (bez naměřené hodnoty)"
        fever_evidence += s.ev_fact("fever_reported")
    if (temp and temp >= 38) or (teplota is not None and teplota >= 1) or chills:
        finding = ", ".join(part for part in [temp_text if (temp and temp >= 38) or (teplota or 0) >= 1 else "", "zimnice/třesavka" if chills else ""] if part)
        text_only = not ((temp and temp >= 38 and "teplota_c" in s.vitals and s.vitals["teplota_c"] >= 38) or (teplota or 0) >= 1)
        if ctx.chemo_window:
            hit("R-FEVER", 4, f"{finding} během chemoterapie" + (" – období nadiru (D7–14)" if ctx.in_nadir else ""), fever_evidence, text_only)
        elif (temp and temp >= 40) or (teplota or 0) >= 3:
            hot = f"teplota {_num(temp)} °C" if temp and temp >= 40 else "teplota nad 40 °C (dotazník)"
            hit("R-HYPERPYREXIA", 4, f"{hot} mimo okno chemoterapie", fever_evidence, text_only)
        elif (temp and temp >= 39) or (teplota or 0) >= 2:
            hit("Y-FEVER", 3, f"{finding} mimo okno chemoterapie", fever_evidence, text_only)
        else:
            hit("Y-FEVER", 2, f"{finding} mimo okno chemoterapie", fever_evidence, text_only)

    if s.idx("pocit") == 4:
        hit("O-GENERAL", 3, "celkový stav „5 = velmi špatně“", s.ev_answer("pocit"))

    # --- breathing, chest, neuro --------------------------------------------------------------------------------
    spo2 = s.vitals.get("spo2")
    resp = s.vitals.get("dechova_frekvence")
    if s.idx("dusnost") == 3 or s.has("dyspnea_rest") or (spo2 is not None and spo2 < 90):
        hit("R-BREATH", 4, "dušnost v klidu" if spo2 is None or spo2 >= 90 else f"SpO2 {_num(spo2)} %", s.ev_answer("dusnost") + s.ev_fact("dyspnea_rest") + s.ev_vital("spo2"), s.idx("dusnost") != 3 and spo2 is None)
    elif (s.has("dyspnea_exertion") or (s.idx("dusnost") or 0) >= 1) and s.has("palpitations"):
        hit("R-BREATH", 4, "dušnost s bušením srdce", s.ev_fact("dyspnea_exertion", "palpitations"), True)
    if s.idx("bol_hrud") == 1 or s.has("chest_pain_new"):
        hit("R-CHEST", 4, "nově vzniklá bolest na hrudi", s.ev_answer("bol_hrud") + s.ev_fact("chest_pain_new"), s.idx("bol_hrud") != 1)
    for fact_type, label in (("confusion", "zmatenost"), ("seizure", "záchvat"), ("limb_weakness_new", "nová slabost končetin"), ("speech_problem", "porucha řeči")):
        if s.has(fact_type):
            hit("R-NEURO", 4, label, s.ev_fact(fact_type), True)
    if s.has("drowsiness_new"):
        marked = any(re.search(MARKED_DROWSINESS, fold(fact.quote)) for fact in s.facts["drowsiness_new"])
        corroborated = (marked and s.lexicon_confirmed("drowsiness_new")) or s.has("breathing_slow") or s.has("confusion") or (resp is not None and resp <= 10)
        if corroborated:
            hit("R-OPIOID" if opioid else "R-NEURO", 4, "nápadná spavost / nereaguje" + (" na opioidech" if opioid else ""), s.ev_fact("drowsiness_new"), True)
        else:
            hit("U-VERIFY", 2, "zmínka o spavosti – ověřit, zda jde o nápadnou změnu (podezření, nepotvrzeno)", s.ev_fact("drowsiness_new"), True)
    if s.has("breathing_slow") or (resp is not None and resp <= 10):
        label = f"zpomalené dýchání {_num(resp)}/min" if resp is not None and resp <= 10 else "zpomalené dýchání"
        hit("R-OPIOID" if opioid else "R-BREATH", 4, label + (" na opioidech" if opioid else ""), s.ev_fact("breathing_slow") + s.ev_vital("dechova_frekvence"), resp is None)
    ospalost = s.scale("ospalost", ESAS)
    if opioid and ospalost is not None and ospalost >= 8:
        earlier = [Signals(item, NluResult()).scale("ospalost", ESAS) for item in filled]
        earlier = [value for value in earlier if value is not None]
        if earlier and ospalost >= earlier[-1] + 2:
            hit("R-OPIOID", 4, f"ESAS ospalost {_num(ospalost)} (dříve {_num(earlier[-1])}) na opioidech", s.ev_answer("ospalost", ESAS))
    if spo2 is not None and 90 <= spo2 < 92:
        hit("O-BREATH", 3, f"SpO2 {_num(spo2)} %", s.ev_vital("spo2"))
    elif spo2 is not None and "spo2" in ctx.baselines and spo2 <= ctx.baselines["spo2"] - 3:
        hit("O-BREATH", 3, f"pokles SpO2 na {_num(spo2)} % (obvykle {_num(ctx.baselines['spo2'])} %)", s.ev_vital("spo2"))
    if s.has("orthopnea"):
        hit("O-BREATH", 3, "nová ortopnoe (spí vsedě / na více polštářích)", s.ev_fact("orthopnea"), True)

    # --- bleeding -------------------------------------------------------------------------------------------------
    sites = {fact.value for fact in s.facts.get("bleeding_site", [])}
    nosebleed = max(s.values("nosebleed_minutes"), default=0)
    if s.has("blood_in_stool") or "stolice" in sites:
        hit("R-BLEED", 4, "krev ve stolici", s.ev_fact("blood_in_stool", "bleeding_site"), True)
    if s.has("black_stool"):
        hit("R-BLEED", 4, "černá stolice", s.ev_fact("black_stool"), True)
    for site, label in (("zvratky", "krev ve zvratcích"), ("moč", "krev v moči"), ("hlen", "vykašlávání krve")):
        if site in sites:
            hit("R-BLEED", 4, label, s.ev_fact("bleeding_site"), True)
    if nosebleed > 20:
        hit("R-BLEED", 4, f"krvácení z nosu {_num(nosebleed)} min", s.ev_fact("nosebleed_minutes"), True)
    if s.has("bleeding_uncontrolled"):
        hit("R-BLEED", 4, "krvácení nejde zastavit", s.ev_fact("bleeding_uncontrolled"), True)
    if s.has("head_injury") and anticoag:
        hit("R-BLEED", 4, "úraz hlavy na antikoagulaci", s.ev_fact("head_injury"), True)
    if anticoag and (s.idx("krvaceni") == 1 or sites or s.has("bruises_new")):
        parts = [f"krvácení ({', '.join(sorted(str(site) for site in sites))})" if sites else "krvácení" if s.idx("krvaceni") == 1 else "", "nové modřiny" if s.has("bruises_new") else ""]
        hit("O-BLEED-ANTICOAG", 3, " a ".join(part for part in parts if part) + " na antikoagulaci", s.ev_answer("krvaceni") + s.ev_answer("krvaceni_popis") + s.ev_fact("bleeding_site", "bruises_new"))
    elif s.idx("krvaceni") == 1 and not (sites & {"nos"} and nosebleed and nosebleed <= 20):
        hit("Y-GRADE2", 2, "krvácení / modřiny (dotazník)", s.ev_answer("krvaceni") + s.ev_answer("krvaceni_popis"))

    # --- diarrhoea ------------------------------------------------------------------------------------------------
    diarrhea_grade = s.diarrhea_grade()
    stool_counts = s.values("stool_count_above_normal")
    stool_text = f"{_num(max(stool_counts))} stolic nad normál" if stool_counts else {1: "průjem do 3 stolic nad normál", 2: "průjem 4–6 stolic nad normál", 3: "průjem ≥ 7 stolic nad normál"}.get(diarrhea_grade, "průjem")
    diarrhea_evidence = s.ev_answer("prujem") + s.ev_fact("stool_count_above_normal", "diarrhea")
    diarrhea_text_only = s.diarrhea_grade_text() > s.diarrhea_grade_form()
    if diarrhea_grade >= 3:
        hit("R-DIARRHEA", 4, f"průjem 3. st. ({stool_text})", diarrhea_evidence, diarrhea_text_only)
    elif diarrhea_grade == 2 and risky_diarrhea:
        drug = "imunoterapii" if io else "irinotekanu" if "irinotecan" in classes else "fluoropyrimidinu"
        hit("O-DIARRHEA-RISK", 3, f"průjem 2. st. ({stool_text}) při {drug}", diarrhea_evidence, diarrhea_text_only)
    elif diarrhea_grade == 2:
        hit("Y-GRADE2", 2, f"průjem 2. st. ({stool_text})", diarrhea_evidence, diarrhea_text_only)
    elif diarrhea_grade == 1 and io_active:
        hit("Y-IO-DIARRHEA", 2, f"{stool_text} během imunoterapie", diarrhea_evidence, diarrhea_text_only)
    if s.has("diarrhea_refractory"):
        hit("O-DIARRHEA-RISK", 3, "průjem nereagující na loperamid", s.ev_fact("diarrhea_refractory"), True)
    if io and diarrhea_grade >= 1 and s.abdominal_pain():
        hit("O-IO-DIARRHEA-PAIN", 3, "průjem s bolestí břicha na imunoterapii", diarrhea_evidence + s.ev_answer("bol_bricho") + s.ev_fact("abdominal_pain_nrs"), diarrhea_text_only)
    if "irinotecan" in classes and diarrhea_grade >= 1 and diarrhea_grade < 3:
        for item in filled:
            if ctx.as_of - item.timestamp <= timedelta(hours=48) and _signals_of(item, ctx).diarrhea_grade() >= 2:
                hit("Y-IRINOTECAN", 2, "průjem po irinotekanu ještě neustoupil (loperamid do 12 h bez průjmu)", diarrhea_evidence)
                break

    # --- vomiting, intake, dehydration --------------------------------------------------------------------------
    vomit_grade = s.vomit_grade()
    vomit_counts = s.values("vomiting_episodes_24h")
    vomit_text = f"zvracení {_num(max(vomit_counts))}× za 24 h" if vomit_counts else {1: "zvracení 1–2× za 24 h", 2: "zvracení 3–5× za 24 h", 3: "zvracení > 5× za 24 h"}.get(vomit_grade, "zvracení")
    vomit_evidence = s.ev_answer("zvraceni") + s.ev_fact("vomiting_episodes_24h")
    signs = s.dehydration_signs()
    severe_intake = s.severe_intake_failure()
    intake_evidence = s.ev_answer("nevolnost") + s.ev_answer("nechutenstvi") + s.ev_answer("afty") + s.ev_fact("cannot_keep_fluids", "liquids_only", "low_fluid_intake")
    vomit_text_only = s.vomit_grade_text() > s.vomit_grade_form()
    if vomit_grade >= 3:
        hit("R-VOMIT", 4, vomit_text, vomit_evidence, vomit_text_only)
    elif vomit_grade >= 1 and severe_intake and signs:
        hit("R-VOMIT", 4, f"{vomit_text}, neudrží tekutiny, {', '.join(signs)}", vomit_evidence + intake_evidence)
    elif vomit_grade == 2 and severe_intake:
        hit("O-VOMIT", 3, f"{vomit_text} a neudrží tekutiny", vomit_evidence + intake_evidence, vomit_text_only)
    elif vomit_grade == 2:
        hit("Y-VOMIT", 2, f"{vomit_text}, pije", vomit_evidence, vomit_text_only)
    no_urine = s.facts.get("no_urine_hours", [])
    if no_urine:
        hours = max((fact.value for fact in no_urine if isinstance(fact.value, (int, float))), default=None)
        if hours is None or hours > 10:
            hit("R-DEHYD", 4, "nemočí > 10 h" if hours else "nemočí", s.ev_fact("no_urine_hours"), True)
        else:
            hit("O-INTAKE", 3, f"nemočí {_num(hours)} h", s.ev_fact("no_urine_hours"), True)
    if s.has("fainting"):
        hit("R-DEHYD", 4, "mdloba", s.ev_fact("fainting"), True)
    if 0 < s.vitals.get("tk_sys", 999) < 90:
        hit("R-DEHYD", 4, f"systolický TK {_num(s.vitals['tk_sys'])} mmHg", s.ev_vital("tk_sys"))
    if severe_intake and len(signs) >= 2:
        hit("R-DEHYD", 4, f"nedostatečný příjem tekutin se známkami dehydratace ({', '.join(signs)})", intake_evidence + s.ev_fact("oliguria", "dizziness_standing") + s.ev_vital("tepova_frekvence"))
    if severe_intake:
        hit("O-INTAKE", 3, "neudrží tekutiny / příjem na minimu", intake_evidence, not any(s.idx(q) is not None and s.idx(q) >= (2 if q == "nevolnost" else 3) for q in ("nevolnost", "nechutenstvi", "afty")))
    pain_uncontrolled = s.idx("spokojenost", PAIN) == 1 or (s.scale("nrs", PAIN) or 0) >= 7 or max(s.values("pain_nrs"), default=0) >= 7
    if (s.idx("afty") == 2 or s.has("liquids_only")) and pain_uncontrolled:
        hit("O-INTAKE", 3, "jen tekutá strava a nekontrolovaná bolest", intake_evidence + s.ev_answer("spokojenost", PAIN) + s.ev_answer("nrs", PAIN))
    if (s.has("oliguria") or s.has("dizziness_standing")) and s.reduced_intake():
        hit("O-INTAKE", 3, f"{', '.join(sign for sign in signs if sign in ('málo močí', 'závrať'))} při sníženém příjmu", intake_evidence + s.ev_fact("oliguria", "dizziness_standing"), True)

    # --- abdomen --------------------------------------------------------------------------------------------------
    no_gas = s.has("no_stool_no_gas")
    if (s.idx("zacpa") == 3 or no_gas) and (s.vomit_present() or s.has("colicky_pain") or (s.idx("bol_bricho") or 0) >= 1 or s.has("abdominal_pain_nrs")):
        hit("R-ILEUS", 4, "zástava stolice/plynů se zvracením nebo kolikovitou bolestí", s.ev_answer("zacpa") + s.ev_fact("no_stool_no_gas", "colicky_pain") + vomit_evidence, s.idx("zacpa") != 3)
    elif s.idx("zacpa") == 3:
        hit("O-GRADE3", 3, "zácpa 3. st. (nezvladatelná)", s.ev_answer("zacpa"))
    if s.vomit_present() and s.abdominal_pain() and ((resp or 0) >= 22 or s.has("fast_breathing")) and (diabetic or io):
        hit("R-DKA", 4, "zvracení + bolest břicha + zrychlené dýchání", vomit_evidence + s.ev_vital("dechova_frekvence") + s.ev_fact("fast_breathing"))

    # --- blood pressure -------------------------------------------------------------------------------------------
    sys_bp, dia_bp = s.vitals.get("tk_sys"), s.vitals.get("tk_dia")
    bp_evidence = s.ev_vital("tk_sys") + s.ev_vital("tk_dia")
    text_bp = [tuple(fact.value) for fact in s.facts.get("blood_pressure", []) if isinstance(fact.value, (list, tuple)) and len(fact.value) == 2]
    if sys_bp is None and dia_bp is None and text_bp:
        sys_bp, dia_bp = max(text_bp)
        bp_evidence = s.ev_fact("blood_pressure")
    bp_text = f"TK {_num(sys_bp or 0)}/{_num(dia_bp or 0)}"
    if sys_bp is not None or dia_bp is not None:
        sys_bp, dia_bp = sys_bp or 0, dia_bp or 0
        high = sys_bp >= 160 or dia_bp >= 100
        neuro_bp = s.has("headache_severe") or s.idx("bol_hlava") == 2 or s.has("vision_problem") or s.has("speech_problem") or s.has("chest_pain_new")
        baseline_sys = ctx.baselines.get("bp_sys")
        if sys_bp >= 180 or dia_bp >= 110:
            hit("R-BP", 4, bp_text, bp_evidence)
        elif high and neuro_bp:
            hit("R-BP", 4, f"{bp_text} se silnou bolestí hlavy / poruchou zraku či řeči", bp_evidence + s.ev_answer("bol_hlava") + s.ev_fact("headache_severe", "vision_problem"))
        elif high and antiangio:
            hit("O-BP-ANTIANGIO", 3, f"{bp_text} na antiangiogenní léčbě", bp_evidence)
        elif antiangio and sys_bp >= 140 and dia_bp >= 90 and (baseline_sys is None or sys_bp >= baseline_sys + 10):
            hit("Y-BP", 2, f"{bp_text} na antiangiogenní léčbě", bp_evidence)
        else:
            readings = [(item.vitalni_funkce["tk_sys"].hodnota, item.vitalni_funkce.get("tk_dia").hodnota if item.vitalni_funkce.get("tk_dia") else 0)
                        for item in filled if item.vitalni_funkce and "tk_sys" in item.vitalni_funkce][-2:] + [(sys_bp, dia_bp)]
            elevated = [reading for reading in readings if (reading[0] >= 140 or reading[1] >= 90) and (baseline_sys is None or reading[0] >= baseline_sys + 10)]
            if len(readings) == 3 and len(elevated) == 3:
                series = " → ".join(f"{_num(a)}/{_num(b)}" for a, b in readings)
                hit("Y-BP", 2, f"opakovaně TK ≥ 140/90 nad obvyklými hodnotami ({series})", bp_evidence)
    if s.has("dizziness_standing") and not hits_with(hits, "O-INTAKE", "R-DEHYD", "R-VOMIT"):
        hit("Y-BP", 2, "závratě při vstávání" + (f", {bp_text}" if sys_bp else ""), s.ev_fact("dizziness_standing") + bp_evidence, True)

    # --- metabolism -----------------------------------------------------------------------------------------------
    glucose = s.vitals.get("glykemie_mmol_l")
    thirst = s.has("thirst_polyuria")
    if glucose is not None and glucose < 4 and "insulin" in classes:
        hit("O-HYPO", 3, f"glykémie {_num(glucose)} mmol/l na inzulinu", s.ev_vital("glykemie_mmol_l"))
    if io and thirst:
        hit("O-IO-ENDO", 3, "velká žízeň a časté močení na imunoterapii", s.ev_fact("thirst_polyuria"), True)
    elif glucose is not None and glucose > 15 and thirst:
        hit("Y-GLUCOSE", 2, f"glykémie {_num(glucose)} mmol/l se žízní a častým močením", s.ev_vital("glykemie_mmol_l") + s.ev_fact("thirst_polyuria"))

    # --- pain -----------------------------------------------------------------------------------------------------
    nrs = s.scale("nrs", PAIN)
    sos = s.scale("sos", PAIN)
    satisfied = s.idx("spokojenost", PAIN)
    text_nrs = max(s.values("pain_nrs"), default=None)
    rescue = max(s.values("rescue_doses_per_day"), default=0)
    pain_evidence = s.ev_answer("nrs", PAIN) + s.ev_answer("sos", PAIN) + s.ev_answer("spokojenost", PAIN) + s.ev_fact("pain_nrs", "rescue_doses_per_day")
    top_nrs = max(value for value in (nrs, text_nrs, 0) if value is not None)
    if top_nrs >= 7 and ((sos or 0) >= 1 or satisfied == 1 or rescue >= 1 or s.has("pain_refractory")):
        hit("O-PAIN", 3, f"bolest NRS {_num(top_nrs)} nepovolí po záchranné dávce", pain_evidence)
    elif (sos or 0) >= 3 or rescue >= 3:
        hit("Y-PAIN", 2, f"{_num(max(sos or 0, rescue))} záchranné dávky analgetik denně", pain_evidence)
    elif top_nrs >= 7 or (top_nrs >= 4 and (satisfied == 1 or (text_nrs or 0) >= 4)):
        hit("Y-PAIN", 2, f"bolest NRS {_num(top_nrs)}", pain_evidence)

    # --- psyche ---------------------------------------------------------------------------------------------------
    if s.has("suicide_plan_intent_means"):
        hit("R-SUICIDE", 4, "myšlenky na sebevraždu s plánem / úmyslem / prostředky", s.ev_fact("suicide_plan_intent_means"), True)
    if s.yes("sebevrazda", PSYCHO) or s.has("suicidal_thoughts"):
        hit("O-PSYCH", 3, "myšlenky na smrt / nejraději by si vzal(a) život", s.ev_answer("sebevrazda", PSYCHO) + s.ev_fact("suicidal_thoughts"), not s.yes("sebevrazda", PSYCHO))
    if s.has("hopelessness"):
        hit("O-PSYCH", 3, "výroky beznaděje", s.ev_fact("hopelessness"), True)
    if s.has("lethal_dose_question"):
        hit("O-PSYCH", 3, "dotaz na smrtelnou dávku léku – ověřit bezpečí", s.ev_fact("lethal_dose_question"), True)
    anxiety, depression, coping = s.scale("uzkost", PSYCHO), s.scale("depresivita", PSYCHO), s.scale("zvladani", PSYCHO)
    if (anxiety or 0) >= 6 or (depression or 0) >= 6 or (coping is not None and coping <= 3):
        parts = [f"úzkost {_num(anxiety)}/10" if (anxiety or 0) >= 6 else "", f"depresivita {_num(depression)}/10" if (depression or 0) >= 6 else "", f"zvládání {_num(coping)}/10" if coping is not None and coping <= 3 else ""]
        hit("Y-PSYCH", 2, "psychoonkologický screening: " + ", ".join(part for part in parts if part), s.ev_answer("uzkost", PSYCHO) + s.ev_answer("depresivita", PSYCHO) + s.ev_answer("zvladani", PSYCHO))
    for item_id, label in (("deprese", "deprese"), ("uzkost", "úzkost")):
        value = s.scale(item_id, ESAS)
        if value is not None and value >= 6:
            hit("Y-PSYCH", 2, f"ESAS {label} {_num(value)}/10", s.ev_answer(item_id, ESAS))
    in_care = s.yes("psychiatr", PSYCHO) or any(event.typ == "kontakt_psycholog" for event in ctx.team_events)
    if s.yes("psycholog", PSYCHO) and not in_care:
        hit("Y-PSYCH", 2, "zájem o psychologa, zatím bez psychologické péče", s.ev_answer("psycholog", PSYCHO))
    if s.has("anxiety"):
        hit("Y-PSYCH", 2, "pacient vyjadřuje strach / obavy", s.ev_fact("anxiety"), True)
    if not any(key.startswith(PSYCHO) for key in s.answers) and not hits_with(hits, "O-PSYCH", "R-SUICIDE"):
        for item in reversed(filled):
            if ctx.as_of - item.timestamp > timedelta(days=14):
                break
            earlier = _signals_of(item, ctx)
            if earlier.yes("sebevrazda", PSYCHO) or earlier.has("suicidal_thoughts") or earlier.has("hopelessness"):
                hit("Y-PSYCH-FOLLOWUP", 2, f"myšlenky na smrt / beznaděj {item.datum:%d. %m.} – trvá sledování", earlier.ev_answer("sebevrazda", PSYCHO) + earlier.ev_fact("suicidal_thoughts", "hopelessness"))
                break
            if any(key.startswith(PSYCHO) for key in earlier.answers):
                break
    if s.has("caregiver_strain"):
        hit("Y-CAREGIVER", 2, "vyčerpání pečující osoby", s.ev_fact("caregiver_strain"), True)
    if s.has("missed_medication"):
        hit("Y-ADHERENCE", 2, "vynechávání léků", s.ev_fact("missed_medication"), True)

    # --- grade-2/3 answers and other toxicities -------------------------------------------------------------------
    grade_answers = [
        ("nevolnost", 1, 2, "nevolnost se sníženým příjmem (2. st.)"),
        ("zacpa", 1, 2, "zácpa 2. st."),
        ("zacpa", 2, 2, "zácpa 2. st. výrazně omezující"),
        ("afty", 1, 2, "afty / bolest při polykání mění příjem (2. st.)"),
        ("afty", 2, 2, "afty – zvládá jen tekutou stravu"),
        ("kuze", 1, 2, "kožní změny bolestivé, omezují činnosti (2. st.)"),
        ("kuze", 2, 3, "kožní změny omezují soběstačnost (3. st.)"),
        ("bol_hlava", 2, 2, "silná bolest hlavy omezující činnosti"),
        ("bol_bricho", 2, 2, "silná bolest břicha"),
        ("bol_klouby", 2, 2, "silná bolest svalů a kloubů"),
        ("moceni", 1, 2, "pálení / řezání při močení"),
        ("dusnost", 2, 2, "dušnost při běžných činnostech (2. st.)"),
    ]
    for qid, index, level, label in grade_answers:
        if s.idx(qid) == index:
            hit("O-GRADE3" if level == 3 else "Y-GRADE2", level, label, s.ev_answer(qid))
    if s.idx("unava") == 2 and ctx.baselines.get("ecog", 0) <= 2:
        hit("Y-GRADE2", 2, "únava omezuje i běžné činnosti", s.ev_answer("unava"))
    if s.idx("bol_klouby") == 1 and "aromatase_inhibitor" in classes:
        hit("Y-GRADE2", 2, "bolest kloubů omezující činnosti na inhibitoru aromatázy (riziko neadherence)", s.ev_answer("bol_klouby"))
    constipation_days = max(s.values("constipation_days"), default=0)
    if constipation_days >= 3 and s.idx("zacpa") is None:
        hit("Y-GRADE2", 2, f"zácpa {_num(constipation_days)} dny", s.ev_fact("constipation_days"), True)
    for fact_type, label in (("nail_fold_inflammation", "zánět nehtového valu (paronychie)"), ("skin_blisters", "puchýře na kůži"), ("port_redness", "zarudnutí / bolest v okolí portu")):
        if s.has(fact_type):
            hit("Y-GRADE2", 2, label, s.ev_fact(fact_type), True)
    if io_active and ((s.has("cough_new") and not copd) or (s.idx("dusnost") or 0) >= 1 or s.has("dyspnea_exertion")):
        level = 3 if (s.idx("dusnost") or 0) >= 2 else 2
        hit("Y-IO-NEW", level, "nový kašel / dušnost na imunoterapii", s.ev_fact("cough_new", "dyspnea_exertion") + s.ev_answer("dusnost"))
    if s.has("headache_severe") and s.idx("bol_hlava") != 2:
        hit("Y-GRADE2", 2, "silná bolest hlavy", s.ev_fact("headache_severe"), True)
    if (s.has("dyspnea_exertion") or s.has("cough_new") and s.has("dyspnea_exertion")) and s.idx("dusnost") is None and not io_active:
        hit("Y-GRADE2", 2, "nová dušnost (zpráva)", s.ev_fact("dyspnea_exertion"), True)
    loss = min(s.values("weight_change_kg"), default=0)
    if loss < 0 and ctx.baselines.get("weight") and -loss >= ctx.baselines["weight"] * 0.05:
        hit("Y-NUTRITION", 2, f"udává úbytek hmotnosti {_num(-loss)} kg", s.ev_fact("weight_change_kg"), True)
    if s.has("calf_swelling_one_side"):
        hit("O-DVT", 3, "jednostranný otok / bolest lýtka", s.ev_fact("calf_swelling_one_side"), True)
    if re.search(r"mozk|glioblast|gliom|c71", fold(ctx.diagnosis)) and (s.idx("bol_hlava") is not None or s.has("headache_severe")) and s.vomit_present():
        hit("O-BRAIN", 3, "bolest hlavy se zvracením u mozkového nádoru", s.ev_answer("bol_hlava") + vomit_evidence)

    neurotoxic_active = "neurotoxic" in classes and not _stopped(ctx, NEUROTOXIC_STEMS)
    function_loss = s.lexicon_confirmed("neuropathy_function_loss")
    if neurotoxic_active and ((s.idx("brneni") or 0) >= 1 or function_loss or s.has("neuropathy_persistent")):
        label = "neuropatie omezující jemnou motoriku" if function_loss or (s.idx("brneni") or 0) >= 1 else "přetrvávající neuropatie mezi cykly"
        hit("Y-NEURO", 2, f"{label} – předat před další aplikací", s.ev_answer("brneni") + s.ev_fact("neuropathy_function_loss", "neuropathy_persistent"))
    if s.has("tinnitus") and "platinum" in classes:
        hit("Y-NEURO", 2, "nový tinnitus na platině – předat před další dávkou", s.ev_fact("tinnitus"), True)

    cardiotoxic_active = "cardiotoxic" in classes and not _stopped(ctx, CARDIOTOXIC_STEMS)
    weight = s.vitals.get("vaha_kg")
    if cardiotoxic_active:
        if any(fact.value == "i ráno" for fact in s.facts.get("edema", [])):
            hit("Y-CARDIO", 2, "otoky i ráno (2. st., šíří se)", s.ev_fact("edema"), True)
        if weight is not None:
            window = [(item.timestamp, item.vitalni_funkce["vaha_kg"].hodnota) for item in filled
                      if item.vitalni_funkce and "vaha_kg" in item.vitalni_funkce and ctx.as_of - item.timestamp <= timedelta(days=7)]
            if window:
                lowest_at, lowest = min(window, key=lambda pair: pair[1])
                if weight - lowest > 2:
                    days = max(1, round((ctx.as_of - lowest_at) / timedelta(days=1)))
                    hit("Y-CARDIO", 2, f"váha +{_num(round(weight - lowest, 1))} kg za {days} dní ({_num(lowest)} → {_num(weight)} kg)", s.ev_vital("vaha_kg"))
    baseline_weight = ctx.baselines.get("weight")
    if weight is not None and baseline_weight and weight <= baseline_weight * 0.95:
        hit("Y-NUTRITION", 2, f"úbytek hmotnosti {_num(round((1 - weight / baseline_weight) * 100, 1))} % ({_num(baseline_weight)} → {_num(weight)} kg)", s.ev_vital("vaha_kg"))
    selfcare, selfcare_base = s.idx("sobestacnost"), ctx.baselines.get("sobestacnost", ctx.baselines.get("ecog"))
    if selfcare is not None and selfcare_base is not None and selfcare >= selfcare_base + 2:
        hit("Y-NUTRITION", 2, f"pokles soběstačnosti o {int(selfcare - selfcare_base)} stupně", s.ev_answer("sobestacnost"))
    if s.intake_score() >= 1 and len(filled) >= 2:
        earlier_scores = [_signals_of(item, ctx).intake_score() for item in filled[-2:]]
        if earlier_scores[0] < earlier_scores[1] < s.intake_score():
            hit("Y-NUTRITION", 2, "postupně klesající příjem (3 záznamy za sebou)", intake_evidence)
    return hits


def hits_with(hits: list[Hit], *rule_ids: str) -> bool:
    return any(item.rule in rule_ids for item in hits)


def contradictions(s: Signals, lang: str) -> tuple[list[Hit], str | None]:
    hits: list[Hit] = []
    question = None
    stool_counts = s.values("stool_count_above_normal")
    if stool_counts and s.diarrhea_grade_text() > s.diarrhea_grade_form():
        count = _num(max(stool_counts))
        form = "dotazník bez průjmu" if s.idx("prujem") is None else "dotazník uvádí nižší počet stolic"
        hits.append(Hit("C-CONTRADICTION", 1, f"rozpor: {form}, zpráva ~{count} stolic za 24 h", s.ev_fact("stool_count_above_normal"), True))
        question = f"Píšete, že máte hnačku asi {count}× za deň – je to tak?" if lang == "sk" else f"Píšete, že máte průjem asi {count}× za den – je to tak?"
    vomit_counts = s.values("vomiting_episodes_24h")
    if vomit_counts and s.vomit_grade_text() > s.vomit_grade_form() and s.vomit_grade_text() >= 2:
        count = _num(max(vomit_counts))
        hits.append(Hit("C-CONTRADICTION", 1, f"rozpor: dotazník uvádí méně zvracení, zpráva {count}× za 24 h", s.ev_fact("vomiting_episodes_24h"), True))
        question = question or (f"Píšete, že ste vracali {count}× za deň – je to tak?" if lang == "sk" else f"Píšete, že jste zvracel(a) {count}× za den – je to tak?")
    text_temp = max(s.values("temperature_c"), default=None)
    form_temp = s.vitals.get("teplota_c")
    if text_temp and text_temp >= 38 and (form_temp is None or form_temp < 38) and (s.idx("teplota") is None or s.idx("teplota") == 0) and s.checkin.dotazniky:
        hits.append(Hit("C-CONTRADICTION", 1, f"rozpor: dotazník bez horečky, zpráva {_num(text_temp)} °C", s.ev_fact("temperature_c"), True))
        question = question or (f"Píšete o teplote {_num(text_temp)} °C – je to tak?" if lang == "sk" else f"Píšete o teplotě {_num(text_temp)} °C – je to tak?")
    if (s.has("blood_in_stool") or s.has("black_stool")) and s.idx("krvaceni") == 0:
        hits.append(Hit("C-CONTRADICTION", 1, "rozpor: dotazník bez krvácení, zpráva uvádí krev ve stolici", s.ev_fact("blood_in_stool", "black_stool"), True))
    return hits, question


def gap_hits(checkin: Checkin, ctx: PatientContext, previous: list[Checkin]) -> list[Hit]:
    missed = 1
    for item in reversed(previous):
        if item.stav != "nevyplneno":
            break
        missed += 1
    high_risk = ctx.in_nadir or "immunotherapy" in ctx.drug_classes
    evidence = [Evidence(zdroj="checkin", citace=f"nevyplněno ({item.datum})", checkin_id=item.checkin_id, datum=str(item.datum)) for item in previous[-(missed - 1):]] if missed > 1 else []
    evidence.append(Evidence(zdroj="checkin", citace=f"nevyplněno ({checkin.datum})", checkin_id=checkin.checkin_id, datum=str(checkin.datum)))
    if missed >= 3 or (missed >= 2 and high_risk):
        return [Hit("Y-GAP", 2, f"{missed} nevyplněné check-iny za sebou – kontaktovat pacienta", evidence)]
    return [Hit("Y-GAP", 1, f"{missed}. nevyplněný check-in – připomenutí", evidence)]


def _context_findings(ctx: PatientContext, checkin: Checkin) -> list[str]:
    findings = []
    cycle, day = checkin.cyklus or ctx.cycle, checkin.den_cyklu or ctx.cycle_day
    regimen = re.sub(r"\s*à \d+ dn[ií]", "", ctx.regimen.split(";")[0]).strip()
    if cycle and day:
        findings.append(f"{regimen}, C{cycle} D{day}" + (" – období nadiru" if ctx.in_nadir else ""))
    else:
        findings.append(regimen)
    labels = {"immunotherapy": "imunoterapie", "fluoropyrimidine": "fluoropyrimidin", "irinotecan": "irinotekan", "anticoagulant": "antikoagulace",
              "antiangiogenic": "antiangiogenní léčba", "cardiotoxic": "kardiotoxická léčba", "opioid": "opioidy"}
    risks = [label for key, label in labels.items() if key in ctx.drug_classes]
    if risks:
        findings.append("rizikové léky: " + ", ".join(risks))
    return findings


def _patient_text(level: int, step: str, contact: str | None, lang: str, addressee: str, warnings: list[str], followup: str | None,
                  hints: list[str], ctx: PatientContext, filled_by: str, use_llm: bool) -> str:
    try:
        from app.triage.responder import compose_reply
        text = compose_reply(level=level, step=step, contact=contact, lang=lang, addressee=addressee, warning_signs=warnings,
                             followup=followup, hints=hints, meds=ctx.meds, use_llm=use_llm, sex=ctx.sex, filled_by=filled_by)
        if isinstance(text, str) and text.strip():
            return text
    except Exception:
        pass
    return fallback_text(level, contact, lang, warnings, followup)


def fallback_text(level: int, contact: str | None, lang: str, warnings: list[str], followup: str | None) -> str:
    signs = ", ".join(warnings[:3])
    sk = lang == "sk"
    if level >= 4:
        contact = without_institution(contact or "155")
        text = (f"Volajte ihneď {contact}. Nečakajte do rána." if sk else f"Volejte ihned {contact}. Nečekejte do rána.")
    elif level == 3:
        if contact and contact.startswith("sloužící"):
            text = ("Vaše ťažkosti treba ešte dnes prebrať s lekárom. Volajte ihneď službukonajúceho lekára 724 590 848." if sk
                    else "Vaše potíže je potřeba ještě dnes probrat s lékařem. Volejte ihned sloužícího lékaře 724 590 848.")
        else:
            text = ("Vaše ťažkosti treba ešte dnes prebrať s lekárom. Lekár vám zavolá do 2 hodín." if sk
                    else "Vaše potíže je potřeba ještě dnes probrat s lékařem. Lékař vám zavolá do 2 hodin.")
        if signs:
            text += f" Pri {signs} volajte 155." if sk else f" Při těchto potížích: {signs} volejte 155."
    elif level == 2:
        when = "do konca nasledujúceho pracovného dňa" if sk else "do konce následujícího pracovního dne"
        text = (f"Váš záznam sme odovzdali tímu monitorovacieho centra, ozve sa vám {when}." if sk
                else f"Váš záznam jsme předali týmu monitorovacího centra, ozve se vám {when}.")
        if signs:
            text += (f" Ak sa objaví {signs}, volajte službukonajúceho lekára 724 590 848 alebo 155." if sk
                     else f" Pokud se objeví {signs}, volejte sloužícího lékaře 724 590 848 nebo 155.")
    else:
        text = ("Ďakujeme, dnešný záznam je v očakávanom rozmedzí. Pokračujte podľa odporúčaní." if sk
                else "Děkujeme, dnešní záznam je v očekávaném rozmezí. Pokračujte podle doporučení.")
        text += (" Ozvite sa skôr, ak budete mať teplotu 38 °C a viac, krv v stolici alebo sa vám výrazne priťaží." if sk
                 else " Ozvěte se dřív, pokud budete mít teplotu 38 °C a více, krev ve stolici nebo se vám výrazně přitíží.")
    if followup:
        text = f"{followup} {text}"
    return text


def _assemble(checkin: Checkin, ctx: PatientContext, hits: list[Hit], followup: str | None, source: str, at: datetime,
              missed_only: bool, use_llm: bool, lang: str | None = None) -> TriageOutput:
    level = max([1, *(item.level for item in hits)])
    step, contact, notify, sla = route(level, at, missed_checkins=missed_only)
    catalog = rules()
    lang = lang or ctx.lang
    addressee = "pacient" if checkin.vyplnil in ("pacient", "patient", "") else "pecujici"
    ordered = sorted(hits, key=lambda item: -item.level)
    findings: list[str] = []
    for item in ordered:
        if item.finding and item.finding not in findings:
            findings.append(item.finding)
    reported = [label for qid, label in SYMPTOM_LABELS.items() if f"{NE}.{qid}" in {f"{fill.dotaznik_id}.{answer.otazka_id}" for fill in checkin.dotazniky for answer in fill.odpovedi}]
    if reported and level == 1:
        findings.append("mírné obtíže (dotazník): " + ", ".join(reported))
    if level >= 2:
        findings += [finding for finding in _context_findings(ctx, checkin) if finding not in findings]
        if addressee == "pecujici":
            findings.append(f"vyplňuje {checkin.vyplnil}")
    if level >= 3 and ctx.advance_directive:
        findings.append(f"dříve vyslovené přání: {ctx.advance_directive}")
    warnings: list[str] = []
    for item in ordered:
        if item.level >= 3 and item.level == catalog.get(item.rule, {}).get("min_level", item.level):
            label = catalog[item.rule]["label"]
            if label not in warnings:
                warnings.append(label)
        elif item.level >= 3 and item.finding not in warnings:
            warnings.append(item.finding)
    fired = []
    for item in ordered:
        if item.rule not in fired and (item.level >= 2 or item.rule == "C-CONTRADICTION"):
            fired.append(item.rule)
    top = [item for item in ordered if item.level == level and item.level >= 2]
    reasons = []
    for item in top:
        rationale = catalog.get(item.rule, {}).get("rationale", "")
        if rationale and rationale not in reasons:
            reasons.append(rationale)
    if level == 1:
        rationale = "Bez varovných příznaků a bez nepříznivého trendu; očekávané mírné obtíže (nejvýše 1. stupeň)." if not missed_only else ""
        if any(item.rule == "Y-GAP" for item in hits):
            rationale = "Nevyplněný check-in – stačí připomenutí; při 3 výpadcích za sebou (u rizikových pacientů 2) kontaktovat pacienta."
    else:
        rationale = " ".join(reasons)
    if any(item.rule == "C-CONTRADICTION" for item in hits):
        rationale = "Zpráva má přednost před dotazníkem – do odpovědi na doplňující otázku platí horší varianta. " + rationale
    if level >= 3 and ctx.advance_directive and "přání" not in rationale:
        rationale += " Dříve vyslovené přání je informací pro tým, není důvodem nedoporučit pomoc (24h linka paliativního týmu / hospic, při nedostupnosti 155)."
    evidence: list[Evidence] = []
    for item in ordered:
        for proof in item.evidence:
            if proof not in evidence:
                evidence.append(proof)
    driving = [item for item in ordered if item.level == level]
    if any(item.rule == "C-CONTRADICTION" for item in hits):
        confidence = "nizka"
    elif level == 1 or any(not item.from_text for item in driving):
        confidence = "vysoka"
    else:
        confidence = "stredni"
    hint_key = f"hint_{lang}"
    patient_warnings: list[str] = []
    for item in ordered:
        hint = catalog.get(item.rule, {}).get(hint_key)
        if item.level >= 2 and hint and hint not in patient_warnings:
            patient_warnings.append(hint)
    palliative = bool(ctx.advance_directive) or "paliativni pece" in fold(ctx.intent)
    gap_hint = ["Y-GAP"] if "Y-GAP" not in fired and any(item.rule == "Y-GAP" for item in hits) else []
    rule_hints = fired + gap_hint + (["PALLIATIVE"] if palliative and level >= 3 else [])
    text = _patient_text(level, step, contact, lang, addressee, patient_warnings, followup, rule_hints, ctx, checkin.vyplnil, use_llm)
    return TriageOutput(
        checkin_id=checkin.checkin_id,
        patient_id=checkin.patient_id,
        uroven=level,
        doporuceny_krok=step,
        upozornit_tym=notify,
        doporuceny_kontakt=contact,
        klicove_nalezy=findings[:8],
        varovne_priznaky=warnings,
        zduvodneni=rationale.strip(),
        doporuceni_pro_pacienta=text,
        doplnujici_otazka=followup,
        pravidla=fired,
        dukazy=evidence[:12],
        jistota=confidence,
        sla_do=sla,
        verze=version(),
        lang=lang,
        adresat=addressee,
        zdroj=source,
        as_of=ctx.as_of,
    )


def triage(checkin: Checkin, ctx: PatientContext, nlu: NluResult, use_llm: bool = True) -> TriageOutput:
    previous = _previous(checkin, ctx)
    if checkin.stav == "nevyplneno":
        hits = gap_hits(checkin, ctx, previous)
        return _assemble(checkin, ctx, hits, None, "checkin", checkin.timestamp, hits[0].level == 2, use_llm)
    signals = Signals(checkin, nlu)
    hits = evaluate(signals, ctx, previous)
    found, followup = contradictions(signals, ctx.lang)
    return _assemble(checkin, ctx, hits + found, followup or _verify_question(hits, ctx.lang), "checkin", checkin.timestamp, False, use_llm)


def _verify_question(hits: list[Hit], lang: str) -> str | None:
    if not hits_with(hits, "U-VERIFY"):
        return None
    return ("Je spavosť výrazne väčšia ako obvykle, alebo sa nedá prebudiť?" if lang == "sk"
            else "Je spavost výrazně větší než obvykle, nebo nejde probudit?")


def triage_chat(patient_id: str, text: str, author: str, ctx: PatientContext, nlu: NluResult, at: datetime, use_llm: bool = True,
                lang: str | None = None) -> TriageOutput:
    lang = lang or ctx.lang
    message = Checkin(
        checkin_id=f"chat-{patient_id}-{at:%Y%m%d%H%M%S}", patient_id=patient_id, datum=at.date(), cas=at.strftime("%H:%M"),
        den_sledovani=0, stav="vyplneno", vyplnil="pacient" if author in ("pacient", "patient") else author, zprava_pacienta=text,
    )
    previous = _previous(message, ctx)
    hits = evaluate(Signals(message, nlu), ctx, previous)
    return _assemble(message, ctx, hits, _verify_question(hits, lang), "chat", at, False, use_llm, lang)
