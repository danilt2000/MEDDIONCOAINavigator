import asyncio
import json
import logging
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.adapters.meddi_json import DATASET_DIRS, load_patients
from app.config import REPO_ROOT
from app.models import PRAGUE, GroundTruth
from app.services import engine

router = APIRouter(prefix="/api", tags=["replay"])
log = logging.getLogger("api.replay")

REPORTS_DIR = REPO_ROOT / "backend" / "reports"
_runs: dict[str, dict] = {}


class ReplayRequest(BaseModel):
    dataset: str = "dev"
    patients: list[str] | None = None
    speed: float = 0  # the console paces playback itself; events stream as fast as the engine runs
    until: datetime | None = None
    use_llm: bool | None = None


def _expected(dataset: str) -> dict[str, GroundTruth]:
    from app.adapters.meddi_json import load_ground_truth

    return load_ground_truth(dataset)


def _run(run_id: str, request: ReplayRequest) -> None:
    run = _runs[run_id]
    until = request.until
    if until is not None:
        until = until.astimezone(PRAGUE) if until.tzinfo else until.replace(tzinfo=PRAGUE)
    wanted = set(request.patients or [])
    patients = [
        patient.model_copy(update={"checkiny": [checkin for checkin in patient.checkiny if until is None or checkin.timestamp <= until]})
        for patient in load_patients(request.dataset)
        if not wanted or patient.patient_id in wanted
    ]
    expected = _expected(request.dataset)
    use_llm = engine.use_llm_default() if request.use_llm is None else request.use_llm
    try:
        for checkin, _ctx, output in engine.replay(patients, use_llm):
            if run["cancelled"]:
                break
            truth = expected.get(checkin.checkin_id)
            run["outputs"].append(output)
            run["events"].append(
                {
                    "checkin_id": checkin.checkin_id,
                    "patient_id": checkin.patient_id,
                    "at": checkin.timestamp.isoformat(),
                    "output": output.model_dump(mode="json"),
                    "expected": truth.model_dump(mode="json") if truth else None,
                }
            )
    except Exception as error:
        log.exception("replay %s failed", run_id)
        run["error"] = str(error)
    finally:
        run["done"] = True


@router.post("/replay")
def start_replay(request: ReplayRequest) -> dict:
    if request.dataset not in DATASET_DIRS:
        raise HTTPException(422, f"dataset must be one of {list(DATASET_DIRS)}")
    run_id = uuid.uuid4().hex[:10]
    _runs[run_id] = {"dataset": request.dataset, "events": [], "outputs": [], "done": False, "error": None, "cancelled": False}
    threading.Thread(target=_run, args=(run_id, request), daemon=True, name=f"replay-{run_id}").start()
    return {"run_id": run_id}


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/replay/{run_id}/events")
async def replay_events(run_id: str) -> StreamingResponse:
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"replay {run_id} not found")

    async def stream():
        sent = 0
        idle = 0.0
        while True:
            events = run["events"]
            while sent < len(events):
                yield _sse("checkin", events[sent])
                sent += 1
                idle = 0.0
            if run["done"] and sent >= len(run["events"]):
                break
            await asyncio.sleep(0.1)
            idle += 0.1
            if idle >= 15:
                yield ": keepalive\n\n"
                idle = 0.0
        if run["error"]:
            yield _sse("error-event", {"message": run["error"]})
        yield _sse("end", {"run_id": run_id, "count": sent})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/eval/{run_id}")
def eval_report(run_id: str) -> dict:
    if run_id.startswith("latest-"):
        dataset = run_id.removeprefix("latest-")
        path = REPORTS_DIR / f"eval_{dataset}.json"
        if dataset not in DATASET_DIRS or not path.exists():
            raise HTTPException(404, f"no CLI report for {dataset}; run scripts/eval.sh {dataset}")
        report = json.loads(path.read_text(encoding="utf-8"))
        report.pop("outputs", None)
        return report
    run = _runs.get(run_id)
    if run is None:
        raise HTTPException(404, f"replay {run_id} not found")
    from app.eval.metrics import evaluate

    report = evaluate(list(run["outputs"]), _expected(run["dataset"]))
    return {**report, "done": run["done"]}
