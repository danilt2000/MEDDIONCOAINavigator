"""Write check-ins and navigator outputs to IRIS FHIR (spec §7, §8.12).

Every writer returns immediately: the work runs on one background thread, which serialises writes (thread-safe,
one licence unit) and skips them when IRIS is down. Nothing here ever raises into the caller. `flush()` waits.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.config import settings
from app.fhir import client
from app.fhir.mappers import (
    LEVEL_NAMES, PRIORITY_RANK, alert_flag, alert_task, chat_communication, checkin_resources, composition,
    fhir_id, grade_observations, iso, navigator_device, patient_resources, provenance, reference_of,
    related_person, reply_communication, risk_assessment,
)
from app.models import PRAGUE, Checkin, DoctorSummary, Patient, QueueTask, TriageOutput

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fhir-writer")
_known_patients: dict[str, Patient] = {}
_last_patient_message: dict[str, str] = {}
_sql_connection = None


def write_checkin(patient: Patient, checkin: Checkin, output: TriageOutput | None = None) -> None:
    _submit(_write_checkin, patient, checkin.model_copy(deep=True), output.model_copy(deep=True) if output else None)


def write_alert(task: QueueTask, output: TriageOutput | None = None) -> None:
    _submit(_write_alert, task.model_copy(deep=True), output.model_copy(deep=True) if output else None)


def write_summary(summary: DoctorSummary) -> None:
    _submit(_write_summary, summary.model_copy(deep=True))


def write_chat(patient_id: str, message: dict) -> None:
    """message = ChatMessage dict {id, at, role, author, text, level_card?, followup_question?, lang?, triage?}."""
    _submit(_write_chat, patient_id, dict(message))


def flush(timeout: float = 120.0) -> None:
    _executor.submit(lambda: None).result(timeout)


def _submit(job, *args) -> None:
    if not settings.fhir_enabled:
        return
    try:
        _executor.submit(_run, job, *args)
    except RuntimeError:  # interpreter shutting down
        pass


def _run(job, *args) -> None:
    if not client.fhir_available():
        return
    try:
        job(*args)
    except Exception:
        log.exception("FHIR write %s failed", job.__name__)


def _patient(patient_id: str) -> Patient | None:
    if patient_id in _known_patients:
        return _known_patients[patient_id]
    try:
        from app.adapters.meddi_json import load_patient
        return load_patient(patient_id)
    except Exception:
        return None


def _dataset(patient: Patient | None) -> str:
    return patient.sada if patient else "dev"


def _ensure_seeded(patient: Patient | None) -> None:
    """Patients posted live (e.g. a hidden-set patient) get their record written once before their first resource."""
    if patient is None or patient.patient_id in _known_patients:
        return
    if client.get(f"Patient/{fhir_id(patient.patient_id)}") is None:
        client.transaction([navigator_device(), *patient_resources(patient)])
    _known_patients[patient.patient_id] = patient


def _output_resources(output: TriageOutput, dataset: str, inputs: list[str], in_response_to: str | None) -> list[dict]:
    risk = risk_assessment(output, dataset, inputs)
    grades = grade_observations(output, dataset)
    reply = reply_communication(output, dataset, in_response_to)
    targets = [reference_of(resource) for resource in (risk, reply, *grades)]
    return [risk, *grades, reply, provenance(targets, inputs, dataset, output.verze, output.as_of, "triage")]


def _write_checkin(patient: Patient, checkin: Checkin, output: TriageOutput | None) -> None:
    _ensure_seeded(patient)
    resources = checkin_resources(patient, checkin)
    inputs = [reference_of(resource) for resource in resources if resource["resourceType"] != "RelatedPerson"]
    if output:
        message = next((reference for reference in inputs if reference.startswith("Communication/")), None)
        resources += _output_resources(output, patient.sada, inputs, message)
    client.transaction(resources)
    if output:
        _save_triage_result(output)


def _write_alert(task: QueueTask, output: TriageOutput | None) -> None:
    patient = _patient(task.patient_id)
    dataset = _dataset(patient)
    _ensure_seeded(patient)
    task_id = fhir_id(task.id)
    open_tasks = client.search("Task", {
        "patient": f"Patient/{fhir_id(task.patient_id)}", "code": "urn:meddi:task|triage-alert",
        "status": "requested,accepted,in-progress", "_count": 50})
    existing = next((resource for resource in open_tasks if resource["id"] != task_id), None)
    extra_notes, extra_identifiers = [], []
    if existing:
        # §8.12: a new escalation of the same patient updates the open Task instead of creating a duplicate
        task_id = existing["id"]
        old_level = next((item.get("valueInteger", 1) for item in existing.get("extension", [])
                          if item["url"].endswith("triage-level")), 1)
        old_priority = existing.get("priority", "routine")
        if PRIORITY_RANK.get(old_priority, 0) > PRIORITY_RANK[task.priority]:
            task.priority = old_priority
        task.uroven = max(task.uroven, old_level)
        extra_identifiers = existing.get("identifier", [])
        extra_notes = [*existing.get("note", []), {
            "time": iso(task.created), "authorString": "MEDDI navigátor",
            "text": f"Nová eskalace: {LEVEL_NAMES[task.uroven]} (úroveň {task.uroven}) – {task.why}"}]
    resource = alert_task(task, output, dataset, task_id, extra_notes, extra_identifiers)
    if existing:
        resource["authoredOn"] = existing.get("authoredOn", resource["authoredOn"])
    flag = alert_flag(task, dataset, task_id)
    evidence = [f"RiskAssessment/{fhir_id(output.checkin_id, 'risk')}"] if output else [f"Patient/{fhir_id(task.patient_id)}"]
    version = output.verze if output else "engine"
    recorded = datetime.now(PRAGUE)
    client.transaction([resource, flag, provenance([reference_of(resource), reference_of(flag)], evidence, dataset,
                                                   version, recorded, "alert")])


def _write_summary(summary: DoctorSummary) -> None:
    patient = _patient(summary.patient_id)
    dataset = _dataset(patient)
    _ensure_seeded(patient)
    document = composition(summary, dataset)
    client.transaction([document, provenance([reference_of(document)], [f"Patient/{fhir_id(summary.patient_id)}"],
                                             dataset, "summary", summary.as_of, "doctor-summary")])


def _write_chat(patient_id: str, message: dict) -> None:
    patient = _patient(patient_id)
    dataset = _dataset(patient)
    _ensure_seeded(patient)
    navigator = message.get("role") == "navigator"
    communication = chat_communication(patient, patient_id, message, dataset,
                                       _last_patient_message.get(patient_id) if navigator else None)
    resources = [communication]
    sender = communication["sender"]
    if sender["reference"].startswith("RelatedPerson/"):
        resources.insert(0, related_person(patient_id, sender["display"], dataset))
    if not navigator:
        _last_patient_message[patient_id] = reference_of(communication)
    output = None
    if message.get("triage"):
        triage = message["triage"]
        output = triage if isinstance(triage, TriageOutput) else TriageOutput.model_validate(triage)
        resources.append(risk_assessment(
            output, dataset, [_last_patient_message.get(patient_id, reference_of(communication))]))
    if navigator or output:
        targets = [reference_of(resource) for resource in resources if resource["resourceType"] != "RelatedPerson"]
        inputs = [_last_patient_message[patient_id]] if patient_id in _last_patient_message else []
        resources.append(provenance(targets, inputs, dataset, output.verze if output else "navigator",
                                    datetime.now(PRAGUE), "chat"))
    client.transaction(resources)


def _save_triage_result(output: TriageOutput) -> None:
    """Projection of every triage into MEDDI.Triage_Result for SQL dashboards; one connection, owned by this thread."""
    global _sql_connection
    try:
        if _sql_connection is None:
            import iris
            _sql_connection = iris.connect(settings.iris_host, settings.iris_port, settings.iris_namespace,
                                           settings.iris_user, settings.iris_password)
        cursor = _sql_connection.cursor()
        cursor.execute("DELETE FROM MEDDI.Triage_Result WHERE CheckinId = ?", [output.checkin_id])
        cursor.execute(
            "INSERT INTO MEDDI.Triage_Result (CheckinId, PatientId, AsOf, TriageLevel, Step, Contact, NotifyTeam, "
            "RuleIds, Confidence, EngineVersion, Source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [output.checkin_id, output.patient_id, output.as_of.astimezone(PRAGUE).strftime("%Y-%m-%d %H:%M:%S"),
             output.uroven, output.doporuceny_krok, output.doporuceny_kontakt, 1 if output.upozornit_tym else 0,
             ",".join(output.pravidla)[:300], output.jistota, output.verze[:40], output.zdroj])
        cursor.close()
    except Exception as error:
        log.warning("MEDDI.Triage_Result insert failed: %s", error)
        try:
            if _sql_connection is not None:
                _sql_connection.close()
        except Exception:
            pass
        _sql_connection = None
