from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import store
from app.services import views

router = APIRouter(prefix="/api", tags=["queue"])

NO_SLA = datetime.max.replace(tzinfo=timezone.utc)


@router.get("/queue")
def queue(status: Literal["open", "all", "completed"] = "open") -> list[dict]:
    store.wait_ready()
    tasks = store.list_tasks()
    if status == "open":
        tasks = [task for task in tasks if task.status != "completed"]
    elif status == "completed":
        tasks = [task for task in tasks if task.status == "completed"]
    tasks.sort(key=lambda task: (-task.uroven, task.sla_do or NO_SLA))
    return [views.queue_item(task) for task in tasks]


class TaskAction(BaseModel):
    action: Literal["accept", "call", "telekonzultace", "close"]
    note: str | None = None
    author: str = "sestra monitorovacího centra"


@router.post("/tasks/{task_id}/action")
def task_action(task_id: str, body: TaskAction) -> dict:
    task = store.apply_task_action(task_id, body.action, body.note, body.author)
    if task is None:
        raise HTTPException(404, f"task {task_id} not found")
    return views.queue_item(task)
