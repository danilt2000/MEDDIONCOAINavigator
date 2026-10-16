"""Navigator tools (spec §9): read-only, pseudonymised, every call logged to backend/logs/mcp.log."""

import functools
import json
import re
import threading
import unicodedata
import time
from datetime import datetime, timedelta

from app.adapters.meddi_json import load_patient
from app.config import settings
from app.models import PRAGUE, Patient, PatientContext, TriageOutput

LOG_FILE = settings.cache_dir.parent / "logs" / "mcp.log"
PHONES = {"monitoring_centre": "MOÚ monitorovací centrum (pracovní dny 7:00–15:30)", "on_duty": "724 590 848", "ems": "155"}
METRIC_VITALS = {"weight": "vaha_kg", "bp_sys": "tk_sys", "bp_dia": "tk_dia", "pulse": "tepova_frekvence",
                 "temperature": "teplota_c", "glucose": "glykemie_mmol_l", "breathing_rate": "dechova_frekvence"}

_log_lock = threading.Lock()
_fallback_now: datetime | None = None
_followups: dict[str, str] = {}
_escalations: dict[str, int] = {}


def _log(tool: str, args: dict, result, started: float) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    preview = json.dumps(result, ensure_ascii=False, default=str)
    line = {"at": datetime.now(PRAGUE).isoformat(timespec="seconds"), "tool": tool, "args": args,
            "ms": round((time.perf_counter() - started) * 1000), "result": preview[:600]}
    with _log_lock, LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")


def logged(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        named = dict(zip(function.__code__.co_varnames, args)) | kwargs
        try:
            result = function(*args, **kwargs)
        except Exception as error:
            _log(function.__name__, named, {"error": type(error).__name__}, started)
            raise
        _log(function.__name__, named, result, started)
        return result

    return wrapper


def store():
    try:
        from app import store as live_store

        return live_store
    except ImportError:
        return None


def now() -> datetime:
    live = store()
    if live is not None:
        return live.get_now()
    return _fallback_now or datetime.now(PRAGUE)


def _parse_at(value: str | datetime | None) -> datetime:
    if value is None or value == "":
        return now()
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return parsed.replace(tzinfo=PRAGUE) if parsed.tzinfo is None else parsed


def context_for(patient: Patient, as_of: datetime) -> PatientContext:
    live = store()
    extra = live.live_checkins(patient.patient_id) if live is not None else []
    try:
        from app.services.engine import build_context
    except ImportError:
        from app.context.builder import build_context
    return build_context(patient, as_of, extra)


def route(level: int, at: datetime) -> tuple[str, str | None, bool, datetime | None]:
    try:
        from app.triage.router import route as engine_route

        return engine_route(level, at)
    except ImportError:
        from app.services.engine import route as api_route

        return api_route(level, at)


def outputs_for(patient_id: str) -> list[TriageOutput]:
    live = store()
    return live.get_patient_outputs(patient_id) if live is not None else []


def palliative_care(ctx: PatientContext) -> bool:
    text = unicodedata.normalize("NFKD", f"{ctx.intent} {ctx.regimen}".lower()).encode("ascii", "ignore").decode()
    return "paliat" in text and bool(re.search(r"pece|starostliv|tym|tim|symptom|hospic", text))


def med_lines(ctx: PatientContext) -> list[dict]:
    return [{"lek": med.lek, "davka": med.davka, "frekvence": med.frekvence, "indikace": med.indikace,
             "pri_potizich": med.pri_potizich} for med in ctx.meds]


@logged
def get_patient_context(patient_id: str, as_of: str | None = None) -> dict:
    """Pseudonymised treatment context: regimen, cycle day, medicines with classes, allergies, last labs, open task."""
    at = _parse_at(as_of)
    ctx = context_for(load_patient(patient_id), at)
    latest_labs: dict[str, dict] = {}
    for lab in sorted(ctx.labs, key=lambda lab: lab.timestamp):
        latest_labs[lab.test] = {"test": lab.test, "hodnota": lab.hodnota, "jednotka": lab.jednotka, "priznak": lab.priznak,
                                 "datum": str(lab.datum)}
    live = store()
    task = live.open_task(patient_id) if live is not None and hasattr(live, "open_task") else None
    return {
        "patient_id": patient_id, "as_of": at.isoformat(timespec="minutes"), "age": ctx.age, "sex": ctx.sex, "lang": ctx.lang,
        "filled_by": ctx.filled_by_default, "diagnosis": ctx.diagnosis, "regimen": ctx.regimen, "intent": ctx.intent,
        "cycle": ctx.cycle, "cycle_day": ctx.cycle_day, "in_nadir": ctx.in_nadir, "chemo_window": ctx.chemo_window,
        "drug_classes": ctx.drug_classes, "meds": med_lines(ctx), "allergies": ctx.allergies,
        "comorbidities": ctx.comorbidities, "palliative": palliative_care(ctx),
        "advance_directive_on_file": bool(ctx.advance_directive), "last_labs": list(latest_labs.values())[-8:],
        "team_events": [{"datum": str(event.datum), "typ": event.typ, "text": event.text} for event in ctx.team_events[-3:]],
        "open_task": {"uroven": task.uroven, "status": task.status, "why": task.why} if task else None,
    }


@logged
def get_recent_checkins(patient_id: str, n: int = 5) -> list[dict]:
    """Last n check-ins (and chat assessments) with level and key findings."""
    ctx = context_for(load_patient(patient_id), now())
    outputs = {output.checkin_id: output for output in outputs_for(patient_id)}
    rows = []
    for checkin in ctx.recent_checkins[-max(1, min(int(n), 10)):]:
        output = outputs.get(checkin.checkin_id)
        rows.append({
            "checkin_id": checkin.checkin_id, "at": checkin.timestamp.isoformat(timespec="minutes"), "stav": checkin.stav,
            "filled_by": checkin.vyplnil, "message": checkin.zprava_pacienta,
            "vitals": {key: value.hodnota for key, value in (checkin.vitalni_funkce or {}).items()},
            "level": output.uroven if output else None, "findings": output.klicove_nalezy if output else [],
        })
    return rows


@logged
def get_trend(patient_id: str, metric: str, days: int = 14) -> dict:
    """Measured series of weight, bp_sys, bp_dia, pulse, temperature, glucose, breathing_rate or pain (NRS)."""
    at = now()
    ctx = context_for(load_patient(patient_id), at)
    since = at - timedelta(days=int(days))
    points = []
    for checkin in ctx.recent_checkins:
        if checkin.timestamp < since:
            continue
        if metric == "pain":
            for fill in checkin.dotazniky:
                for answer in fill.odpovedi:
                    if answer.otazka_id in ("nrs", "bolest") and isinstance(answer.odpoved_index, int):
                        points.append({"at": checkin.timestamp.isoformat(timespec="minutes"), "value": answer.odpoved_index,
                                       "source": fill.dotaznik_id})
        elif metric in METRIC_VITALS and checkin.vitalni_funkce and METRIC_VITALS[metric] in checkin.vitalni_funkce:
            measurement = checkin.vitalni_funkce[METRIC_VITALS[metric]]
            points.append({"at": checkin.timestamp.isoformat(timespec="minutes"), "value": measurement.hodnota,
                           "source": measurement.zdroj})
    return {"metric": metric, "days": days, "points": points}


@logged
def search_guidance(query: str, lang: str = "cs") -> list[dict]:
    """Top 5 approved patient-facing passages from IRIS Vector Search (Audience = patient only)."""
    from app.agent.vectors import search_guidance as vector_search

    lang = "sk" if lang == "sk" else "cs"
    try:
        return [{"cite": hit["source"], "text": hit["text"], "score": hit["score"]} for hit in vector_search(query, lang, "patient", 5)]
    except Exception:
        return []


@logged
def get_contact(level: int, at: str | None = None) -> dict:
    """The right contact for a level at a time (router), plus opening hours and phone numbers."""
    when = _parse_at(at)
    step, contact, notify, sla = route(max(1, min(int(level), 4)), when)
    return {"level": level, "step": step, "contact": contact, "notify_team": notify,
            "sla_do": sla.isoformat(timespec="minutes") if sla else None, "phones": PHONES}


@logged
def ask_followup(patient_id: str, question: str) -> dict:
    """Post one follow-up question to the patient; only one open question at a time."""
    if patient_id in _followups:
        return {"posted": False, "open_question": _followups[patient_id]}
    _followups[patient_id] = question.strip()
    return {"posted": True, "open_question": _followups[patient_id]}


def pop_followup(patient_id: str) -> str | None:
    return _followups.pop(patient_id, None)


def set_floor(patient_id: str, level: int) -> None:
    _escalations[patient_id] = level


@logged
def escalate(patient_id: str, level: int, reason: str, evidence: str = "") -> dict:
    """Create or raise the patient's task. Can only raise the current level, never lower it."""
    level = int(level)
    live = store()
    task = live.open_task(patient_id) if live is not None and hasattr(live, "open_task") else None
    current = max(_escalations.get(patient_id, 1), task.uroven if task else 1)
    if level <= current or level not in (2, 3, 4):
        return {"raised": False, "level": current, "note": "eskalace může úroveň jen zvýšit"}
    at = now()
    step, contact, notify, sla = route(level, at)
    output = TriageOutput(
        checkin_id=f"{patient_id}-CHAT-ESC-{at:%Y%m%d%H%M%S}", patient_id=patient_id, uroven=level, doporuceny_krok=step,
        upozornit_tym=True, doporuceny_kontakt=contact, klicove_nalezy=[reason], varovne_priznaky=[],
        zduvodneni=f"Navigátor eskaloval z chatu: {reason}" + (f" ({evidence})" if evidence else ""),
        doporuceni_pro_pacienta="", pravidla=["NAV-ESCALATE"], sla_do=sla, verze="navigator 0.1.0", zdroj="chat", as_of=at,
    )
    _escalations[patient_id] = level
    if live is not None:
        live.record_output(None, output)
        live.raise_task(output)
    return {"raised": True, "level": level, "contact": contact}
