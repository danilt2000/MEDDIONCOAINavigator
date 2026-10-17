"""Thread-safe in-memory state of the running demo: clock, processed check-ins, tasks, chat.

Public helpers for other modules: get_now(), get_dataset(), get_patient_outputs(patient_id),
add_chat(patient_id, message), list_chat(patient_id), raise_task(output), live_checkins(patient_id).
"""

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta

from app.adapters.meddi_json import load_patient, load_patients
from app.models import PRAGUE, Checkin, DoctorSummary, Patient, QueueTask, TaskNote, TeamEvent, TriageOutput

log = logging.getLogger("uvicorn.error")

DEFAULT_NOW = "2026-09-09T21:50:00+02:00"
PRIORITY_BY_LEVEL = {2: "routine", 3: "urgent", 4: "stat"}
PRIORITY_RANK = {"routine": 0, "urgent": 1, "stat": 2}
OWNER_IN_HOURS = "monitorovací centrum"
OWNER_OUT_OF_HOURS = "sloužící lékař MOÚ"

_lock = threading.RLock()
_ready = threading.Event()
_state: dict = {}


def _parse_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=PRAGUE) if parsed.tzinfo is None else parsed.astimezone(PRAGUE)


def _empty_state(now: datetime, dataset: str, generation: int) -> dict:
    return {
        "generation": generation,
        "now_base": now,
        "set_at": time.monotonic(),
        "dataset": dataset,
        "checkins": {},
        "outputs": {},
        "live": {},
        "tasks": {},
        "chat": {},
        "summaries": {},
        "nlu": {},
        "accepted_at": {},
        "team_events": {},
    }


def get_now() -> datetime:
    _ensure_started()
    with _lock:
        return _state["now_base"] + timedelta(seconds=time.monotonic() - _state["set_at"])


def generation() -> int:
    """Changes whenever the demo state is reset; part of cache keys derived from the store."""
    _ensure_started()
    return _state["generation"]


def get_dataset() -> str:
    _ensure_started()
    return _state["dataset"]


def wait_ready(timeout: float = 60) -> bool:
    _ensure_started()
    return _ready.wait(timeout)


def set_demo_state(now: datetime | None = None, dataset: str | None = None) -> None:
    """Reset the store and replay the dataset up to the new demo NOW in the background."""
    _ensure_started()
    with _lock:
        new_now = (now.astimezone(PRAGUE) if now.tzinfo else now.replace(tzinfo=PRAGUE)) if now else get_now()
        new_dataset = dataset or _state.get("dataset", "dev")
        _state.clear()
        _state.update(_empty_state(new_now, new_dataset, _next_generation()))
        _ready.clear()
        generation = _state["generation"]
    threading.Thread(target=_replay_until_now, args=(generation,), daemon=True, name="demo-replay").start()


_generation_counter = 0


def _next_generation() -> int:
    global _generation_counter
    _generation_counter += 1
    return _generation_counter


_started = False


def _ensure_started() -> None:
    global _started
    if _started:
        return
    with _lock:
        if _started:
            return
        _started = True
        now = _parse_now(os.environ.get("DEMO_NOW", DEFAULT_NOW))
        dataset = os.environ.get("DEMO_DATASET", "dev")
        replay_on_start = os.environ.get("DEMO_REPLAY", "1") != "0"
        _state.update(_empty_state(now, dataset, _next_generation()))
        generation = _state["generation"]
    if replay_on_start:
        threading.Thread(target=_replay_until_now, args=(generation,), daemon=True, name="demo-replay").start()
    else:
        _ready.set()


def _replay_until_now(generation: int) -> None:
    from app.services import engine

    started = time.monotonic()
    try:
        with _lock:
            now = _state["now_base"]
            dataset = _state["dataset"]
        patients = [
            patient.model_copy(update={"checkiny": [checkin for checkin in patient.checkiny if checkin.timestamp <= now]})
            for patient in load_patients(dataset)
        ]
        count = 0
        for checkin, _ctx, output in engine.replay(patients, engine.use_llm_default()):
            with _lock:
                if _state.get("generation") != generation:
                    return
                record_output(checkin, output)
                if output.uroven >= 2:
                    _close_handled_tasks(dataset, output.as_of, output.patient_id)
                    raise_task(output, side_effects=False)
            count += 1
        with _lock:
            if _state.get("generation") == generation:
                _close_handled_tasks(dataset, now)
        log.info("demo replay of %s up to %s: %d check-ins in %.1f s", dataset, now, count, time.monotonic() - started)
        if os.environ.get("DEMO_WRITE_FHIR") == "1":
            _write_history_to_fhir(dataset)
    except Exception:
        log.exception("demo replay failed")
    finally:
        with _lock:
            if _state.get("generation") == generation:
                _ready.set()


def _write_history_to_fhir(dataset: str) -> None:
    """Optional: put the replayed history into IRIS too (the writers queue it on their own thread)."""
    from app.fhir.writers import write_alert, write_checkin

    patients = {patient.patient_id: patient for patient in load_patients(dataset)}
    for checkin in all_checkins():
        write_checkin(patients[checkin.patient_id], checkin, get_output(checkin.checkin_id))
    for task in list_tasks():
        output = get_output(task.checkin_id) if task.checkin_id else None
        if output is not None:
            write_alert(task, output)


def _close_handled_tasks(dataset: str, at: datetime, patient_id: str | None = None) -> None:
    """Replayed history: a team event after the task or an SLA that ran out by `at` means the team handled it."""
    events = {patient.patient_id: patient.udalosti_tymu for patient in load_patients(dataset)}
    for task in _state["tasks"].values():
        if task.status == "completed" or (patient_id and task.patient_id != patient_id):
            continue
        handled = [event for event in events.get(task.patient_id, []) if task.created <= event.timestamp <= at]
        if handled:
            first = min(handled, key=lambda event: event.timestamp)
            task.notes.append(TaskNote(at=first.timestamp, author=first.autor, text=f"{first.typ}: {first.text}"))
            task.status = "completed"
        elif task.sla_do and task.sla_do < at:
            task.notes.append(TaskNote(at=task.sla_do, author=task.owner, text="Vyřízeno (historie před začátkem dema)."))
            task.status = "completed"


def record_output(checkin: Checkin | None, output: TriageOutput, live: bool = False, nlu=None) -> None:
    with _lock:
        if checkin is not None:
            _state["checkins"][checkin.checkin_id] = checkin
            if live:
                _state["live"].setdefault(checkin.patient_id, []).append(checkin)
        _state["outputs"][output.checkin_id] = output
        if nlu is not None:
            _state["nlu"][output.checkin_id] = nlu


def live_checkins(patient_id: str) -> list[Checkin]:
    _ensure_started()
    with _lock:
        return list(_state["live"].get(patient_id, []))


def all_checkins() -> list[Checkin]:
    """Check-ins the system has processed (replayed history + live), chronological."""
    _ensure_started()
    with _lock:
        return sorted(_state["checkins"].values(), key=lambda checkin: checkin.timestamp)


def get_checkin(checkin_id: str) -> Checkin | None:
    with _lock:
        return _state["checkins"].get(checkin_id)


def get_nlu(checkin_id: str):
    with _lock:
        return _state["nlu"].get(checkin_id)


def get_output(checkin_id: str) -> TriageOutput | None:
    _ensure_started()
    with _lock:
        return _state["outputs"].get(checkin_id)


def all_outputs() -> list[TriageOutput]:
    _ensure_started()
    with _lock:
        return sorted(_state["outputs"].values(), key=lambda output: output.as_of)


def get_patient_outputs(patient_id: str) -> list[TriageOutput]:
    """All triage outputs of the patient (check-ins and chat), oldest first."""
    return [output for output in all_outputs() if output.patient_id == patient_id]


def add_chat(patient_id: str, message: dict) -> dict:
    """Append a ChatMessage dict ({id, at, role, author, text, level_card?, followup_question?}); fills id and at."""
    _ensure_started()
    stored = {"id": uuid.uuid4().hex[:12], "at": get_now().isoformat(), **message}
    if isinstance(stored["at"], datetime):
        stored["at"] = stored["at"].isoformat()
    with _lock:
        _state["chat"].setdefault(patient_id, []).append(stored)
    return stored


def list_chat(patient_id: str) -> list[dict]:
    _ensure_started()
    with _lock:
        return list(_state["chat"].get(patient_id, []))


def clear_chat(patient_id: str) -> None:
    _ensure_started()
    with _lock:
        _state["chat"].pop(patient_id, None)


def set_summary(summary: DoctorSummary) -> None:
    with _lock:
        _state["summaries"][summary.patient_id] = summary


def get_summary(patient_id: str) -> DoctorSummary | None:
    with _lock:
        return _state["summaries"].get(patient_id)


def _why(output: TriageOutput) -> str:
    parts = output.varovne_priznaky or output.klicove_nalezy[:2]
    return "; ".join(parts) if parts else output.zduvodneni


def raise_task(output: TriageOutput, side_effects: bool = True) -> QueueTask | None:
    """Create a task for level >= 2, or raise the patient's open task (never lowers level or priority)."""
    from app.triage.router import is_working_hours

    if output.uroven < 2:
        return None
    _ensure_started()
    priority = PRIORITY_BY_LEVEL[output.uroven]
    out_of_hours = not is_working_hours(output.as_of)
    with _lock:
        task = open_task(output.patient_id)
        if task is None:
            task = QueueTask(
                id=f"T-{output.patient_id}-{len(_state['tasks']) + 1:03d}",
                patient_id=output.patient_id,
                checkin_id=output.checkin_id,
                uroven=output.uroven,
                priority=priority,
                owner=OWNER_OUT_OF_HOURS if out_of_hours else OWNER_IN_HOURS,
                why=_why(output),
                out_of_hours=out_of_hours,
                created=output.as_of,
                sla_do=output.sla_do,
            )
            _state["tasks"][task.id] = task
        else:
            task.notes.append(TaskNote(at=output.as_of, author="navigátor", text=f"Nová eskalace (úroveň {output.uroven}, {output.zdroj}): {_why(output)}"))
            if output.uroven > task.uroven:
                task.checkin_id = output.checkin_id
                task.uroven = output.uroven
                task.why = _why(output)
                task.out_of_hours = out_of_hours
                task.owner = OWNER_OUT_OF_HOURS if out_of_hours else OWNER_IN_HOURS
                task.created = output.as_of
                task.sla_do = output.sla_do
                if task.status in ("accepted", "in-progress"):
                    task.status = "requested"
                    _state["accepted_at"].pop(task.id, None)
            if PRIORITY_RANK[priority] > PRIORITY_RANK[task.priority]:
                task.priority = priority
            if output.sla_do and (task.sla_do is None or output.sla_do < task.sla_do):
                task.sla_do = output.sla_do
        snapshot = task.model_copy(deep=True)
    if side_effects:
        from app.services.side_effects import dispatch_alert

        dispatch_alert(snapshot, output)
    return snapshot


def accepted_at(task_id: str) -> datetime | None:
    with _lock:
        return _state["accepted_at"].get(task_id)


def sla_breached(task: QueueTask, now: datetime) -> bool:
    """Open and past its SLA without having been taken over in time."""
    accepted = accepted_at(task.id)
    return task.status != "completed" and task.sla_do is not None and task.sla_do < now and (accepted is None or accepted > task.sla_do)


def replay_cutoff() -> datetime:
    """Dataset check-ins up to this moment were replayed at demo start; later ones are the demo's future."""
    _ensure_started()
    with _lock:
        return _state["now_base"]


def open_task(patient_id: str) -> QueueTask | None:
    with _lock:
        candidates = [task for task in _state["tasks"].values() if task.patient_id == patient_id and task.status != "completed"]
        return max(candidates, key=lambda task: task.created) if candidates else None


def list_tasks() -> list[QueueTask]:
    _ensure_started()
    with _lock:
        return [task.model_copy(deep=True) for task in _state["tasks"].values()]


def get_task(task_id: str) -> QueueTask | None:
    with _lock:
        task = _state["tasks"].get(task_id)
        return task.model_copy(deep=True) if task else None


TASK_TRANSITIONS = {"accept": "accepted", "call": "in-progress", "telekonzultace": "in-progress", "close": "completed"}
STATUS_ORDER = ["requested", "accepted", "in-progress", "completed"]
TEAM_EVENT_TYPE = {"call": "kontakt_sestra", "telekonzultace": "telekonzultace", "close": "kontakt_sestra"}
ACTION_TEXT = {"accept": "Převzato", "call": "Telefonát s pacientem", "telekonzultace": "Telekonzultace", "close": "Uzavřeno"}


def apply_task_action(task_id: str, action: str, note: str | None, author: str) -> QueueTask | None:
    with _lock:
        task = _state["tasks"].get(task_id)
        if task is None:
            return None
        text = ACTION_TEXT[action] + (f": {note}" if note else "")
        at = get_now()
        task.notes.append(TaskNote(at=at, author=author, text=text))
        target = TASK_TRANSITIONS[action]
        if STATUS_ORDER.index(target) > STATUS_ORDER.index(task.status):
            task.status = target
        if action != "close":
            _state["accepted_at"].setdefault(task_id, at)
        if action in TEAM_EVENT_TYPE and (action != "close" or note):
            _add_team_event(task.patient_id, at, TEAM_EVENT_TYPE[action], author, text)
        return task.model_copy(deep=True)


def _add_team_event(patient_id: str, at: datetime, kind: str, author: str, text: str) -> None:
    local = at.astimezone(PRAGUE)
    start = load_patient(patient_id).obdobi_sledovani["od"]
    event = TeamEvent(
        patient_id=patient_id,
        datum=local.date(),
        cas=local.strftime("%H:%M"),
        den_sledovani=(local.date() - start).days + 1,
        typ=kind,
        autor=author,
        text=text,
    )
    _state["team_events"].setdefault(patient_id, []).append(event)


def with_live_events(patient: Patient) -> Patient:
    """The patient with team events recorded from queue actions, so the engine sees that the team is acting."""
    _ensure_started()
    with _lock:
        events = list(_state["team_events"].get(patient.patient_id, []))
    return patient.model_copy(update={"udalosti_tymu": [*patient.udalosti_tymu, *events]}) if events else patient


def live_team_event_count(patient_id: str) -> int:
    with _lock:
        return len(_state["team_events"].get(patient_id, []))


def minutes_to_accept() -> list[float]:
    with _lock:
        return [
            (accepted - _state["tasks"][task_id].created).total_seconds() / 60
            for task_id, accepted in _state["accepted_at"].items()
        ]
