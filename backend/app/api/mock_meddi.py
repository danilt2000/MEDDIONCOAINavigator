from datetime import datetime, timezone

from fastapi import APIRouter, Body

router = APIRouter(prefix="/mock/meddi", tags=["mock-meddi"])

# ponytail: in-memory, lost on restart; it only stands in for the real MEDDI monitoring-centre inbox
received: list[dict] = []


@router.post("/requests", status_code=201)
def receive(payload: dict = Body(...)) -> dict:
    item = {"id": len(received) + 1, "received_at": datetime.now(timezone.utc).isoformat(), "payload": payload}
    received.append(item)
    return item


@router.get("/requests")
def list_received() -> list[dict]:
    return received
