"""Patient timeline, trend series and doctor summary."""

import threading
from datetime import datetime, timedelta
from functools import lru_cache

from app import store
from app.models import PRAGUE, Checkin, DoctorSummary, Fact, Patient
from app.services import engine

METRICS = {
    "weight": ("kg", "vaha_kg"),
    "bp_sys": ("mmHg", "tk_sys"),
    "bp_dia": ("mmHg", "tk_dia"),
    "pulse": ("/min", "tepova_frekvence"),
    "temperature": ("°C", "teplota_c"),
    "glucose": ("mmol/l", "glykemie_mmol_l"),
    "stools": ("stolic nad normál / 24 h", None),
    "pain": ("NRS", None),
}
STOOLS_BY_PRUJEM_INDEX = {0: 3, 1: 5, 2: 7, 3: 7}
FACT_BY_METRIC = {"stools": "stool_count_above_normal", "pain": "pain_nrs", "temperature": "temperature_c"}
LEVEL_LABEL = {1: "zelená", 2: "žlutá", 3: "oranžová", 4: "červená"}
VITAL_LABELS = [("teplota_c", "T {} °C"), ("tepova_frekvence", "tep {}"), ("glykemie_mmol_l", "glykémie {}"), ("vaha_kg", "váha {} kg"), ("spo2", "SpO2 {} %")]


def _demo_patient(patient: Patient, as_of: datetime) -> tuple[Patient, list[Checkin]]:
    """(patient with the dataset check-ins the demo knows, live check-ins). Live views see the history replayed at demo
    start plus live check-ins; the replay console asking about a later moment sees the dataset only."""
    if as_of > store.get_now():
        return patient, []
    cutoff = store.replay_cutoff()
    return patient.model_copy(update={"checkiny": [checkin for checkin in patient.checkiny if checkin.timestamp <= cutoff]}), store.live_checkins(patient.patient_id)


def patient_checkins(patient: Patient, as_of: datetime) -> list[Checkin]:
    known, live = _demo_patient(patient, as_of)
    return sorted((checkin for checkin in [*known.checkiny, *live] if checkin.timestamp <= as_of), key=lambda checkin: checkin.timestamp)


def _number(value: float) -> str:
    return f"{value:g}"


def _checkin_detail(checkin: Checkin) -> str:
    parts = []
    if checkin.zprava_pacienta:
        parts.append(f"„{checkin.zprava_pacienta}“")
    vitals = checkin.vitalni_funkce or {}
    if "tk_sys" in vitals and "tk_dia" in vitals:
        parts.append(f"TK {_number(vitals['tk_sys'].hodnota)}/{_number(vitals['tk_dia'].hodnota)}")
    parts += [label.format(_number(vitals[name].hodnota)) for name, label in VITAL_LABELS if name in vitals]
    warnings = [fill.nejvyssi_barva for fill in checkin.dotazniky if fill.nejvyssi_barva in ("zluta", "cervena")]
    if warnings:
        parts.append(f"dotazník: {'červená' if 'cervena' in warnings else 'žlutá'} odpověď")
    parts += checkin.prilohy
    return " · ".join(parts) or "bez potíží"


def timeline(patient: Patient, as_of: datetime) -> list[dict]:
    items = []
    for checkin in patient_checkins(patient, as_of):
        output = store.get_output(checkin.checkin_id)
        if checkin.stav == "nevyplneno":
            items.append({"kind": "missed", "at": checkin.timestamp, "title": "Check-in nevyplněn", "detail": "", "level": output.uroven if output else None, "ref": checkin.checkin_id})
            continue
        filled_by = "" if checkin.vyplnil == "pacient" else f" (vyplnil/a: {checkin.vyplnil})"
        title = f"Check-in{filled_by}" + (f" · {LEVEL_LABEL[output.uroven]}" if output else "")
        items.append({"kind": "checkin", "at": checkin.timestamp, "title": title, "detail": _checkin_detail(checkin), "level": output.uroven if output else None, "ref": checkin.checkin_id})
    draws: dict[str, list] = {}
    for lab in patient.laboratore:
        if lab.timestamp <= as_of:
            draws.setdefault(lab.odber_id, []).append(lab)
    for draw_id, labs in draws.items():
        values = ", ".join(f"{lab.test} {_number(lab.hodnota)} {lab.jednotka}" + (f" ({lab.priznak})" if lab.priznak else "") for lab in labs)
        items.append({"kind": "lab", "at": labs[0].timestamp, "title": f"Odběr · {labs[0].misto}", "detail": values, "level": None, "ref": draw_id})
    for number, event in enumerate(patient.udalosti_tymu, 1):
        if event.timestamp <= as_of:
            items.append({"kind": "team_event", "at": event.timestamp, "title": f"{event.typ.replace('_', ' ')} · {event.autor}", "detail": event.text, "level": None, "ref": f"{patient.patient_id}-E{number:02d}"})
    for number, exam in enumerate(patient.vysetreni, 1):
        if exam.datum < as_of.astimezone(PRAGUE).date():
            at = datetime(exam.datum.year, exam.datum.month, exam.datum.day, tzinfo=PRAGUE)
            items.append({"kind": "exam", "at": at, "title": exam.vysetreni, "detail": exam.vysledek, "level": None, "ref": f"{patient.patient_id}-X{number:02d}"})
    for message in store.list_chat(patient.patient_id):
        at = datetime.fromisoformat(message["at"])
        if at <= as_of:
            card = message.get("level_card") or {}
            who = "navigátor" if message.get("role") == "navigator" else message.get("author", "pacient")
            items.append({"kind": "chat", "at": at, "title": f"Chat · {who}", "detail": message.get("text", ""), "level": card.get("uroven"), "ref": message["id"]})
    items.sort(key=lambda item: item["at"])
    return [{**item, "at": item["at"].isoformat()} for item in items]


@lru_cache(maxsize=4096)
def _lexicon_facts(patient_id: str, checkin_id: str) -> tuple[Fact, ...]:
    from app.adapters.meddi_json import load_patient

    patient = load_patient(patient_id)
    checkin = next((item for item in [*patient.checkiny, *store.live_checkins(patient_id)] if item.checkin_id == checkin_id), None)
    if checkin is None:
        return ()
    ctx = engine.build_context(patient, checkin.timestamp, store.live_checkins(patient_id))
    return tuple(engine.analyze(checkin, ctx, use_llm=False).facts)


def _facts(checkin: Checkin) -> list[Fact]:
    stored = store.get_nlu(checkin.checkin_id)
    if stored is not None:
        return stored.facts
    if not (checkin.zprava_pacienta or checkin.prilohy):
        return []
    return list(_lexicon_facts(checkin.patient_id, checkin.checkin_id))


def _answers(checkin: Checkin) -> dict[tuple[str, str], object]:
    return {(fill.dotaznik_id, answer.otazka_id): answer for fill in checkin.dotazniky for answer in fill.odpovedi}


def _fact_point(checkin: Checkin, metric: str) -> tuple[float, str] | None:
    fact_type = FACT_BY_METRIC.get(metric)
    if fact_type is None:
        return None
    for fact in _facts(checkin):
        if fact.type == fact_type and isinstance(fact.value, (int, float)) and not isinstance(fact.value, bool):
            return float(fact.value), fact.source
    return None


def _points(checkin: Checkin, metric: str) -> list[tuple[float, str]]:
    """One value per check-in: a measurement, else the exact count from the message (beats the form), else the form."""
    vitals = checkin.vitalni_funkce or {}
    vital = METRICS[metric][1]
    if vital and vital in vitals:
        return [(vitals[vital].hodnota, vitals[vital].zdroj)]
    fact = _fact_point(checkin, metric)
    if fact is not None:
        return [fact]
    answers = _answers(checkin)
    if metric == "stools":
        answer = answers.get(("nezadouci_ucinky", "prujem"))
        if answer is not None and isinstance(answer.odpoved_index, int):
            return [(STOOLS_BY_PRUJEM_INDEX.get(answer.odpoved_index, 7), "dotaznik")]
    if metric == "pain":
        for key in (("bolest_analgeticka_terapie", "nrs"), ("esas", "bolest")):
            value = getattr(answers.get(key), "odpoved", None)
            if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
                return [(float(value), "dotaznik")]
    return []


def trend(patient: Patient, metric: str, days: int, now: datetime) -> dict:
    since = now - timedelta(days=days)
    points = []
    for checkin in patient_checkins(patient, now):
        if checkin.timestamp < since or checkin.stav == "nevyplneno":
            continue
        for value, source in _points(checkin, metric):
            points.append({"at": checkin.timestamp.isoformat(), "value": value, "source": source})
    return {"metric": metric, "unit": METRICS[metric][0], "points": points}


def _with_missing_outputs(patient: Patient, as_of: datetime, outputs: list) -> list:
    """A summary asked for a moment after the demo clock (replay console) also needs the check-ins up to that moment."""
    known = {output.checkin_id for output in outputs}
    live = _demo_patient(patient, as_of)[1]
    for checkin in patient_checkins(patient, as_of):
        if checkin.checkin_id not in known:
            outputs.append(engine.run_checkin(patient, checkin, live, False)[2])
    return sorted(outputs, key=lambda output: output.as_of)


_summary_cache: dict[tuple, DoctorSummary] = {}
_summary_lock = threading.Lock()


def summary(patient: Patient, as_of: datetime, reason: str | None, explicit: bool) -> DoctorSummary:
    outputs = [output for output in store.get_patient_outputs(patient.patient_id) if output.as_of <= as_of]
    if as_of > store.get_now():
        dataset_ids = {checkin.checkin_id for checkin in patient.checkiny}
        outputs = [output for output in outputs if output.checkin_id in dataset_ids]
    if explicit:
        outputs = _with_missing_outputs(patient, as_of, outputs)
    last_id = outputs[-1].checkin_id if outputs else None
    if not explicit:
        stored = store.get_summary(patient.patient_id)
        if stored is not None and (not outputs or stored.as_of >= outputs[-1].as_of):
            return stored
    reason = reason or "souhrn na vyžádání"
    key = (store.generation(), patient.patient_id, as_of.isoformat() if explicit else last_id, reason, len(outputs), len(patient.udalosti_tymu))
    with _summary_lock:
        cached = _summary_cache.get(key)
    if cached is not None:
        return cached
    known, live = _demo_patient(patient, as_of)
    ctx = engine.build_context(known, as_of, live)
    built = engine.build_summary(patient, ctx, outputs, reason)
    with _summary_lock:
        _summary_cache[key] = built
    return built
