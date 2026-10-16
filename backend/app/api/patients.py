from datetime import datetime

from fastapi import APIRouter, HTTPException

from app import store
from app.adapters.meddi_json import DATASET_DIRS, load_patient, load_patients
from app.models import PRAGUE, Patient
from app.services import history, views

router = APIRouter(prefix="/api", tags=["patients"])


def get_patient(patient_id: str) -> Patient:
    try:
        return load_patient(patient_id)
    except KeyError:
        raise HTTPException(404, f"patient {patient_id} not found") from None


@router.get("/patients")
def list_patients(dataset: str = "dev") -> list[dict]:
    if dataset not in DATASET_DIRS:
        raise HTTPException(422, f"dataset must be one of {list(DATASET_DIRS)}")
    store.wait_ready()
    return [views.patient_list_item(patient) for patient in load_patients(dataset)]


@router.get("/patients/{patient_id}")
def patient_detail(patient_id: str) -> dict:
    patient = get_patient(patient_id)
    store.wait_ready()
    return views.patient_detail(patient)


def _as_of(value: str | None) -> datetime:
    if not value:
        return store.get_now()
    try:
        as_of = datetime.fromisoformat(value.strip().replace(" ", "+"))
    except ValueError:
        raise HTTPException(422, f"as_of must be an ISO datetime, got {value!r}") from None
    return as_of.astimezone(PRAGUE) if as_of.tzinfo else as_of.replace(tzinfo=PRAGUE)


@router.get("/patients/{patient_id}/context")
def patient_context(patient_id: str, as_of: str | None = None) -> dict:
    get_patient(patient_id)
    return views.context_at(patient_id, _as_of(as_of)).model_dump(mode="json")


@router.get("/patients/{patient_id}/timeline")
def patient_timeline(patient_id: str, as_of: str | None = None) -> list[dict]:
    patient = get_patient(patient_id)
    store.wait_ready()
    return history.timeline(store.with_live_events(patient), _as_of(as_of))


@router.get("/patients/{patient_id}/trends")
def patient_trends(patient_id: str, metric: str = "weight", days: int = 30) -> dict:
    patient = get_patient(patient_id)
    if metric not in history.METRICS:
        raise HTTPException(422, f"metric must be one of {list(history.METRICS)}")
    store.wait_ready()
    return history.trend(patient, metric, days, store.get_now())


@router.get("/patients/{patient_id}/triage")
def patient_triage(patient_id: str) -> list[dict]:
    get_patient(patient_id)
    store.wait_ready()
    return [output.model_dump(mode="json") for output in reversed(store.get_patient_outputs(patient_id))]


@router.get("/patients/{patient_id}/summary")
def patient_summary(patient_id: str, as_of: str | None = None, reason: str | None = None) -> dict:
    patient = get_patient(patient_id)
    store.wait_ready()
    return history.summary(store.with_live_events(patient), _as_of(as_of), reason, explicit=as_of is not None or reason is not None).model_dump(mode="json")
