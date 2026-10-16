"""Response shapes of packages/api/src/types.ts built from patients, contexts and the store."""

import unicodedata
from datetime import datetime
from functools import lru_cache

from app import store
from app.adapters.meddi_json import load_patient
from app.models import PRAGUE, Patient, PatientContext, QueueTask
from app.services import engine

BADGE_BY_CLASS = {
    "immunotherapy": "IO",
    "fluoropyrimidine": "FP",
    "irinotecan": "irinotekan",
    "anticoagulant": "antikoagulace",
    "antiangiogenic": "antiangiogenní",
    "cardiotoxic": "kardiotoxická",
    "opioid": "opioid",
}
BADGE_ORDER = ["IO", "FP", "irinotekan", "antikoagulace", "antiangiogenní", "kardiotoxická", "opioid", "paliativní", "nadir"]
KEYWORD_BADGES = {
    "IO": ("ipilimumab", "nivolumab", "atezolizumab", "pembrolizumab"),
    "FP": ("5-fu", "fluorouracil", "kapecitabin", "capecitabin", "folfox", "folfiri"),
    "irinotekan": ("irinotekan", "irinotecan", "folfiri"),
    "antikoagulace": ("warfarin", "enoxaparin", "rivaroxaban", "apixaban", "dabigatran"),
    "antiangiogenní": ("sunitinib", "bevacizumab"),
    "kardiotoxická": ("doxorubicin", "epirubicin", "trastuzumab", "r-chop", "ac ("),
    "opioid": ("morfin", "oramorph", "oxykodon", "fentanyl", "hydromorfon", "tramadol"),
}


def _plain(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(char))


@lru_cache(maxsize=4096)
def _cached_context(patient_id: str, as_of_minute: str, generation: int, live_checkins: int, live_events: int) -> PatientContext:
    patient = store.with_live_events(load_patient(patient_id))
    return engine.build_context(patient, datetime.fromisoformat(as_of_minute), store.live_checkins(patient_id))


def context_at(patient_id: str, as_of: datetime | None = None) -> PatientContext:
    moment = (as_of or store.get_now()).astimezone(PRAGUE).replace(second=0, microsecond=0)
    return _cached_context(patient_id, moment.isoformat(), store.generation(), len(store.live_checkins(patient_id)), store.live_team_event_count(patient_id))


def risk_badges(patient: Patient, ctx: PatientContext) -> list[str]:
    badges = {BADGE_BY_CLASS[name] for name in ctx.drug_classes if name in BADGE_BY_CLASS}
    if not ctx.drug_classes:
        drug_text = _plain(" ".join([patient.lecba.rezim, *patient.lecba.leky, *(med.lek for med in ctx.meds)]))
        badges |= {badge for badge, words in KEYWORD_BADGES.items() if any(word in drug_text for word in words)}
    if "paliat" in _plain(patient.lecba.zamer + " " + patient.lecba.rezim):
        badges.add("paliativní")
    if ctx.in_nadir:
        badges.add("nadir")
    return [badge for badge in BADGE_ORDER if badge in badges]


def patient_list_item(patient: Patient) -> dict:
    ctx = context_at(patient.patient_id)
    outputs = [output for output in store.get_patient_outputs(patient.patient_id) if output.zdroj == "checkin"]
    latest = outputs[-1] if outputs else None
    task = store.open_task(patient.patient_id)
    return {
        "patient_id": patient.patient_id,
        "dataset": patient.sada,
        "name": patient.demografie.jmeno_fiktivni,
        "age": patient.demografie.vek,
        "sex": patient.demografie.pohlavi,
        "lang": patient.demografie.jazyk,
        "diagnosis": patient.diagnoza.diagnoza,
        "regimen": patient.lecba.rezim,
        "cycle": ctx.cycle,
        "cycle_day": ctx.cycle_day,
        "risk_badges": risk_badges(patient, ctx),
        "filled_by": patient.demografie.vyplnuje,
        "last_level": latest.uroven if latest else None,
        "last_checkin_at": latest.as_of.isoformat() if latest else None,
        "open_task": task.model_dump(mode="json") if task else None,
    }


def patient_detail(patient: Patient) -> dict:
    ctx = context_at(patient.patient_id)
    return {
        **patient_list_item(patient),
        "stage": patient.diagnoza.stadium,
        "icd10": patient.diagnoza.mkn10,
        "intent": patient.lecba.zamer,
        "ecog": patient.ecog_vychozi,
        "comorbidities": patient.komorbidity,
        "allergies": patient.alergie,
        "advance_directive": patient.predem_vyslovena_prani,
        "meds": [med.model_dump(mode="json") for med in ctx.meds or patient.leky],
        "monitoring": {key: value.isoformat() for key, value in patient.obdobi_sledovani.items()},
    }


def queue_item(task: QueueTask) -> dict:
    patient = load_patient(task.patient_id)
    checkin = store.get_checkin(task.checkin_id) if task.checkin_id else None
    cycle_day = checkin.den_cyklu if checkin else context_at(task.patient_id).cycle_day
    return {
        **task.model_dump(mode="json"),
        "patient_name": patient.demografie.jmeno_fiktivni,
        "age": patient.demografie.vek,
        "regimen": patient.lecba.rezim,
        "cycle_day": cycle_day,
    }
