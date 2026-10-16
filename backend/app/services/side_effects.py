"""Background writes to IRIS (FHIR) and the outbound alert; never block or fail a request."""

import logging
import threading

import httpx

from app.config import settings
from app.models import Checkin, DoctorSummary, Patient, QueueTask, TriageOutput

log = logging.getLogger("api.side_effects")


def _background(name: str, work) -> None:
    def run() -> None:
        try:
            work()
        except Exception:
            log.exception("%s failed", name)

    threading.Thread(target=run, daemon=True, name=name).start()


def dispatch_checkin(patient: Patient, checkin: Checkin, output: TriageOutput, summary: DoctorSummary | None) -> None:
    def work() -> None:
        try:
            from app.fhir.writers import write_checkin, write_summary
        except ImportError:
            return
        write_checkin(patient, checkin, output)
        if summary is not None:
            write_summary(summary)

    _background("fhir-checkin", work)


def alert_payload(task: QueueTask, output: TriageOutput) -> dict:
    """The proposed MEDDI `POST /requests` body (spec §11)."""
    return {
        "patient_id": task.patient_id,
        "priority": task.priority,
        "category": f"triage-{task.uroven}",
        "title": f"Úroveň {task.uroven}: {task.why}",
        "why": output.zduvodneni,
        "due_at": task.sla_do.isoformat() if task.sla_do else None,
        "summary": None,
        "evidence": [evidence.model_dump() for evidence in output.dukazy],
        "task_id": task.id,
        "checkin_id": output.checkin_id,
        "owner": task.owner,
        "contact": output.doporuceny_kontakt,
    }


def _send_alert(task: QueueTask, output: TriageOutput) -> None:
    payload = alert_payload(task, output)
    try:
        from app.interop.alerts import send_alert_via_iris
    except ImportError:
        send_alert_via_iris = None
    if send_alert_via_iris is not None and send_alert_via_iris(payload):
        return
    httpx.post(f"{settings.meddi_mock_url}/requests", json=payload, timeout=5)


def dispatch_alert(task: QueueTask, output: TriageOutput) -> None:
    def work() -> None:
        try:
            from app.fhir.writers import write_alert
        except ImportError:
            write_alert = None
        if write_alert is not None:
            try:
                write_alert(task, output)
            except Exception:
                log.exception("FHIR write_alert failed")
        _send_alert(task, output)

    _background("alert", work)
