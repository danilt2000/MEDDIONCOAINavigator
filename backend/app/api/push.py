from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.patients import get_patient
from app.config import settings
from app.services import push

router = APIRouter(prefix="/api/push", tags=["push"])

NOT_CONFIGURED = "Web Push není nastaven (chybí VAPID klíče)."
NO_DEVICE = "Pacient nemá žádné zařízení se zapnutými upozorněními."
UNKNOWN_SERVICE = "Neznámá push služba (podporujeme Google, Apple, Mozilla a Microsoft)."


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=256)


class Subscription(BaseModel):
    endpoint: str = Field(pattern=r"^https://\S+$", max_length=2048)
    keys: SubscriptionKeys


class SubscribeIn(BaseModel):
    patient_id: str
    subscription: Subscription
    user_agent: str = Field(default="", max_length=512)


class UnsubscribeIn(BaseModel):
    endpoint: str


class SendIn(BaseModel):
    patient_id: str
    kind: Literal["checkin", "team"]
    device_id: str | None = None


def _require_configured() -> None:
    if not push.configured():
        raise HTTPException(503, NOT_CONFIGURED)


@router.get("/key")
def public_key() -> dict:
    _require_configured()
    return {"public_key": settings.vapid_public_key}


@router.post("/subscribe")
def subscribe(body: SubscribeIn) -> dict:
    get_patient(body.patient_id)
    if not push.known_service(body.subscription.endpoint):
        raise HTTPException(422, UNKNOWN_SERVICE)
    return push.subscribe(body.patient_id, body.subscription.endpoint, body.subscription.keys.model_dump(), body.user_agent)


@router.post("/unsubscribe")
def unsubscribe(body: UnsubscribeIn) -> dict:
    return {"removed": push.unsubscribe(body.endpoint)}


@router.get("/devices")
def devices(patient_id: str | None = None) -> list[dict]:
    return push.devices(patient_id)


@router.get("/templates")
def templates(patient_id: str) -> list[dict]:
    return push.templates(get_patient(patient_id))


@router.post("/send")
def send(body: SendIn) -> dict:
    patient = get_patient(body.patient_id)
    _require_configured()
    result = push.send(patient, body.kind, body.device_id)
    if result is None:
        raise HTTPException(404, NO_DEVICE)
    return result
