from fastapi import APIRouter, Body, HTTPException
from pydantic import ValidationError

from app import store
from app.api.patients import get_patient
from app.services import pipeline

router = APIRouter(prefix="/api", tags=["checkins"])


@router.post("/checkins")
def post_checkin(body: dict = Body(...)) -> dict:
    if not body.get("patient_id"):
        raise HTTPException(422, "patient_id is required")
    patient = get_patient(body["patient_id"])
    store.wait_ready()
    try:
        checkin = pipeline.normalize_checkin(body, patient)
    except ValidationError as error:
        raise HTTPException(422, error.errors(include_url=False, include_context=False)) from None
    return pipeline.process_checkin(patient, checkin).model_dump(mode="json")


@router.get("/checkins/{checkin_id}/triage")
def checkin_triage(checkin_id: str) -> dict:
    output = store.get_output(checkin_id)
    if output is None:
        raise HTTPException(404, f"no triage for {checkin_id}")
    return output.model_dump(mode="json")
