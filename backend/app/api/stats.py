import statistics
from collections.abc import Iterator
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.adapters.meddi_json import load_patient
from app.models import PRAGUE, Checkin, TriageOutput
from app.services import views
from app.services.symptoms import SYMPTOMS, fact_grades, symptom_grades
from app.triage.router import is_working_hours

router = APIRouter(prefix="/api", tags=["stats"])

LEVELS = ("1", "2", "3", "4")
PRIORITY_BY_LEVEL = {1: "routine", 2: "routine", 3: "urgent", 4: "stat"}


def _day(moment: datetime) -> date:
    return moment.astimezone(PRAGUE).date()


def _seen() -> list[tuple[Checkin, TriageOutput | None]]:
    """Check-ins processed so far (replayed history + live) with their outputs, up to the demo NOW."""
    store.wait_ready()
    now = store.get_now()
    return [(checkin, store.get_output(checkin.checkin_id)) for checkin in store.all_checkins() if checkin.timestamp <= now]


def _chat_turns() -> list[TriageOutput]:
    """Chat messages triaged so far, one output each (the escalate tool's own records are left out)."""
    now = store.get_now()
    return [output for output in store.all_outputs() if output.zdroj == "chat" and "-CHAT-ESC-" not in output.checkin_id and output.as_of <= now]


def _alerting(output: TriageOutput | None) -> bool:
    """Level 2+ that alerted the team; a chat message inside an already open episode only repeats it."""
    return output is not None and output.uroven >= 2 and "NAV-OPEN-EPISODE" not in output.pravidla


def _reports(seen: list) -> Iterator[tuple[str, date, dict[str, int], TriageOutput | None]]:
    """Symptom reports: filled check-ins (questionnaire, measured temperature) and chat messages (their NLU facts)."""
    for checkin, output in seen:
        if checkin.stav != "nevyplneno":
            yield checkin.patient_id, _day(checkin.timestamp), symptom_grades(checkin), output
    for output in _chat_turns():
        nlu = store.get_nlu(output.checkin_id)
        yield output.patient_id, _day(output.as_of), fact_grades(nlu.facts) if nlu else {}, output


def _range(seen: list, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    start = date_from or min((_day(checkin.timestamp) for checkin, _ in seen), default=_day(store.get_now()))
    return start, date_to or _day(store.get_now())


@router.get("/stats/kpi")
def kpi() -> dict:
    seen = _seen()
    now = store.get_now()
    today = _day(now)
    by_level = dict.fromkeys(LEVELS, 0)
    for checkin, output in seen:
        if output and _day(checkin.timestamp) == today:
            by_level[str(output.uroven)] += 1
    open_tasks = [task for task in store.list_tasks() if task.status != "completed"]
    minutes = store.minutes_to_accept()
    return {
        "today_by_level": by_level,
        "open_tasks": len(open_tasks),
        "sla_breached": sum(1 for task in open_tasks if store.sla_breached(task, now)),
        "missed_checkins": sum(1 for checkin, _ in seen if checkin.stav == "nevyplneno" and checkin.timestamp >= now - timedelta(days=7)),
        "median_minutes_to_accept": round(statistics.median(minutes), 1) if minutes else None,
    }


@router.get("/stats/daily")
def daily(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to")) -> list[dict]:
    seen = _seen()
    start, end = _range(seen, date_from, date_to)
    rows = {start + timedelta(days=offset): {"by_level": dict.fromkeys(LEVELS, 0), "checkins": 0, "missed": 0} for offset in range((end - start).days + 1)}
    for checkin, output in seen:
        row = rows.get(_day(checkin.timestamp))
        if row is None:
            continue
        if checkin.stav == "nevyplneno":
            row["missed"] += 1
        else:
            row["checkins"] += 1
        if output:
            row["by_level"][str(output.uroven)] += 1
    for output in _chat_turns():
        row = rows.get(_day(output.as_of))
        if row is not None and _alerting(output):
            row["by_level"][str(output.uroven)] += 1
    return [{"date": day.isoformat(), **row} for day, row in rows.items()]


@router.get("/stats/symptoms")
def symptoms(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to")) -> list[dict]:
    seen = _seen()
    start, end = _range(seen, date_from, date_to)
    totals = {symptom: {"patients": set(), "alerts": 0, "reports": 0} for symptom in SYMPTOMS}
    for patient_id, day, grades, output in _reports(seen):
        if not start <= day <= end:
            continue
        for symptom in grades:
            totals[symptom]["patients"].add(patient_id)
            totals[symptom]["reports"] += 1
            if _alerting(output):
                totals[symptom]["alerts"] += 1
    rows = [{"symptom": symptom, "patients": len(total["patients"]), "alerts": total["alerts"], "reports": total["reports"]} for symptom, total in totals.items()]
    return sorted((row for row in rows if row["reports"]), key=lambda row: (-row["alerts"], -row["reports"]))


@router.get("/stats/patient/{patient_id}/symptoms")
def patient_symptoms(patient_id: str) -> list[dict]:
    totals: dict[str, dict] = {}
    for reporter, _day_, grades, _output in _reports(_seen()):
        if reporter != patient_id:
            continue
        for symptom, grade in grades.items():
            row = totals.setdefault(symptom, {"symptom": symptom, "max_grade": 0, "reports": 0})
            row["max_grade"] = max(row["max_grade"], grade)
            row["reports"] += 1
    return sorted(totals.values(), key=lambda row: (-row["max_grade"], -row["reports"]))


@router.get("/stats/day/{day}")
def day_drilldown(day: date) -> list[dict]:
    found = [(output, checkin.timestamp, checkin.den_cyklu) for checkin, output in _seen()] + [(output, output.as_of, None) for output in _chat_turns()]
    worst: dict[str, tuple[TriageOutput, int | None]] = {}
    for output, moment, cycle_day in found:
        if _alerting(output) and _day(moment) == day:
            current = worst.get(output.patient_id)
            if current is None or output.uroven >= current[0].uroven:
                worst[output.patient_id] = (output, cycle_day)
    tasks = store.list_tasks()
    rows = []
    for patient_id, (output, cycle_day) in worst.items():
        candidates = [task for task in tasks if task.patient_id == patient_id and _day(task.created) <= day]
        task = next((task for task in tasks if task.checkin_id == output.checkin_id), None) or max(candidates, key=lambda task: task.created, default=None)
        patient = load_patient(patient_id)
        out_of_hours = not is_working_hours(output.as_of)
        rows.append(
            {
                "id": task.id if task else f"D-{output.checkin_id}",
                "patient_id": patient_id,
                "checkin_id": output.checkin_id,
                "uroven": output.uroven,
                "priority": PRIORITY_BY_LEVEL[output.uroven],
                "status": task.status if task else "completed",
                "owner": task.owner if task else (store.OWNER_OUT_OF_HOURS if out_of_hours else store.OWNER_IN_HOURS),
                "why": "; ".join(output.varovne_priznaky or output.klicove_nalezy[:2]) or output.zduvodneni,
                "out_of_hours": out_of_hours,
                "created": output.as_of.isoformat(),
                "sla_do": output.sla_do.isoformat() if output.sla_do else None,
                "notes": [note.model_dump(mode="json") for note in task.notes] if task else [],
                "patient_name": patient.demografie.jmeno_fiktivni,
                "age": patient.demografie.vek,
                "regimen": patient.lecba.rezim,
                "cycle_day": cycle_day if cycle_day is not None else views.context_at(patient_id, output.as_of).cycle_day,
            }
        )
    return sorted(rows, key=lambda row: (-row["uroven"], row["created"]))


@router.get("/stats/symptom/{symptom}")
def symptom_drilldown(symptom: str) -> list[dict]:
    if symptom not in SYMPTOMS:
        raise HTTPException(404, f"unknown symptom; use one of {list(SYMPTOMS)}")
    series: dict[str, dict[str, int]] = {}
    for patient_id, report_day, grades, _output in _reports(_seen()):
        day = report_day.isoformat()
        patient_series = series.setdefault(patient_id, {})
        patient_series[day] = max(patient_series.get(day, 0), grades.get(symptom, 0))
    rows = []
    for patient_id, by_day in series.items():
        if not any(by_day.values()):
            continue
        patient = load_patient(patient_id)
        rows.append(
            {
                "patient_id": patient_id,
                "name": patient.demografie.jmeno_fiktivni,
                "regimen": patient.lecba.rezim,
                "risk_badges": views.risk_badges(patient, views.context_at(patient_id)),
                "max_grade": max(by_day.values()),
                "series": [{"date": day, "grade": grade} for day, grade in sorted(by_day.items())],
            }
        )
    return sorted(rows, key=lambda row: -row["max_grade"])
