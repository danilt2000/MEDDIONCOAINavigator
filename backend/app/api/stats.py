import statistics
from datetime import date, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.adapters.meddi_json import load_patient
from app.models import PRAGUE, Checkin, TriageOutput
from app.services import views
from app.services.symptoms import SYMPTOMS, symptom_grades
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
    return [{"date": day.isoformat(), **row} for day, row in rows.items()]


@router.get("/stats/symptoms")
def symptoms(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to")) -> list[dict]:
    seen = _seen()
    start, end = _range(seen, date_from, date_to)
    totals = {symptom: {"patients": set(), "alerts": 0, "reports": 0} for symptom in SYMPTOMS}
    for checkin, output in seen:
        if not start <= _day(checkin.timestamp) <= end:
            continue
        for symptom in symptom_grades(checkin):
            totals[symptom]["patients"].add(checkin.patient_id)
            totals[symptom]["reports"] += 1
            if output and output.uroven >= 2:
                totals[symptom]["alerts"] += 1
    rows = [{"symptom": symptom, "patients": len(total["patients"]), "alerts": total["alerts"], "reports": total["reports"]} for symptom, total in totals.items()]
    return sorted((row for row in rows if row["reports"]), key=lambda row: (-row["alerts"], -row["reports"]))


@router.get("/stats/patient/{patient_id}/symptoms")
def patient_symptoms(patient_id: str) -> list[dict]:
    totals: dict[str, dict] = {}
    for checkin, _ in _seen():
        if checkin.patient_id != patient_id or checkin.stav == "nevyplneno":
            continue
        for symptom, grade in symptom_grades(checkin).items():
            row = totals.setdefault(symptom, {"symptom": symptom, "max_grade": 0, "reports": 0})
            row["max_grade"] = max(row["max_grade"], grade)
            row["reports"] += 1
    return sorted(totals.values(), key=lambda row: (-row["max_grade"], -row["reports"]))


@router.get("/stats/day/{day}")
def day_drilldown(day: date) -> list[dict]:
    worst: dict[str, tuple[Checkin, TriageOutput]] = {}
    for checkin, output in _seen():
        if output and output.uroven >= 2 and _day(checkin.timestamp) == day:
            current = worst.get(checkin.patient_id)
            if current is None or output.uroven >= current[1].uroven:
                worst[checkin.patient_id] = (checkin, output)
    tasks = store.list_tasks()
    rows = []
    for patient_id, (checkin, output) in worst.items():
        candidates = [task for task in tasks if task.patient_id == patient_id and _day(task.created) <= day]
        task = next((task for task in tasks if task.checkin_id == checkin.checkin_id), None) or max(candidates, key=lambda task: task.created, default=None)
        patient = load_patient(patient_id)
        out_of_hours = not is_working_hours(output.as_of)
        rows.append(
            {
                "id": task.id if task else f"D-{checkin.checkin_id}",
                "patient_id": patient_id,
                "checkin_id": checkin.checkin_id,
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
                "cycle_day": checkin.den_cyklu,
            }
        )
    return sorted(rows, key=lambda row: (-row["uroven"], row["created"]))


@router.get("/stats/symptom/{symptom}")
def symptom_drilldown(symptom: str) -> list[dict]:
    if symptom not in SYMPTOMS:
        raise HTTPException(404, f"unknown symptom; use one of {list(SYMPTOMS)}")
    series: dict[str, dict[str, int]] = {}
    for checkin, _ in _seen():
        if checkin.stav == "nevyplneno":
            continue
        grade = symptom_grades(checkin).get(symptom, 0)
        day = _day(checkin.timestamp).isoformat()
        patient_series = series.setdefault(checkin.patient_id, {})
        patient_series[day] = max(patient_series.get(day, 0), grade)
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
