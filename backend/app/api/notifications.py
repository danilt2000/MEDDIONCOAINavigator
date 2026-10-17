from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.services import notifications

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class RuleUpdate(BaseModel):
    id: str
    enabled: bool
    params: dict[str, int | str] = {}


@router.get("/rules")
def rules() -> list[dict]:
    return list(notifications.load_rules().values())


@router.put("/rules")
def update_rules(body: list[RuleUpdate]) -> list[dict]:
    try:
        return list(notifications.save_rules([update.model_dump() for update in body]).values())
    except ValueError as error:
        raise HTTPException(422, str(error)) from None


@router.get("/preview")
def preview() -> dict:
    store.wait_ready()
    return notifications.preview()


@router.post("/rules/{rule_id}/run")
def run(rule_id: str) -> list[dict]:
    if notifications.RULES.get(rule_id, {}).get("kind") not in ("time", "event"):
        raise HTTPException(404, f"Pravidlo {rule_id} nelze spustit.")
    store.wait_ready()
    return notifications.run_now(rule_id)


@router.get("/log")
def log() -> list[dict]:
    return notifications.get_log()
