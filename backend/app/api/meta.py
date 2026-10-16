import socket
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.adapters.meddi_json import DATASET_DIRS, load_questionnaires
from app.config import settings

router = APIRouter(prefix="/api", tags=["meta"])

VERSION = "0.1.0"
CONTACTS = {
    "monitoring_centre": {"phone": "543 131 111", "hours": "Po–Pá 7:00–15:30"},
    "on_duty": {"phone": "724 590 848"},
    "ems": {"phone": "155"},
}

_health_cache: dict = {"at": 0.0, "value": None}


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _fhir_up() -> bool:
    try:
        from app.fhir.client import fhir_available
    except ImportError:
        fhir_available = None
    if fhir_available is not None:
        return bool(fhir_available())
    try:
        response = httpx.get(
            f"{settings.fhir_base}/metadata",
            auth=(settings.iris_user, settings.iris_password),
            headers={"Accept": "application/fhir+json"},
            timeout=2,
        )
        return response.status_code == 200
    except httpx.HTTPError:
        return False


@router.get("/health")
def health() -> dict:
    if _health_cache["value"] is None or time.monotonic() - _health_cache["at"] > 30:
        _health_cache["value"] = {
            "iris": _port_open(settings.iris_host, settings.iris_port),
            "fhir": settings.fhir_enabled and _fhir_up(),
            "llm": settings.llm_enabled and bool(settings.openai_api_key),
            "mcp": _port_open("localhost", 8101),
            "version": VERSION,
        }
        _health_cache["at"] = time.monotonic()
    return _health_cache["value"]


class DemoStateIn(BaseModel):
    now: datetime | None = None
    dataset: str | None = None


def _demo_state() -> dict:
    return {"now": store.get_now().isoformat(), "dataset": store.get_dataset()}


@router.get("/demo/state")
def get_demo_state() -> dict:
    return _demo_state()


@router.post("/demo/state")
def post_demo_state(body: DemoStateIn) -> dict:
    if body.dataset is not None and body.dataset not in DATASET_DIRS:
        raise HTTPException(422, f"dataset must be one of {list(DATASET_DIRS)}")
    store.set_demo_state(body.now, body.dataset)
    store.wait_ready(120)
    return _demo_state()


@router.get("/questionnaires")
def questionnaires() -> list:
    return load_questionnaires()


@router.get("/contacts")
def contacts() -> dict:
    return CONTACTS
