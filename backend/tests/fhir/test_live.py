from datetime import datetime, timedelta

import pytest

from app.adapters.meddi_json import dataset_dir
from app.fhir import client, writers
from app.models import PRAGUE, DoctorSummary, Patient, QueueTask, TriageOutput

pytestmark = pytest.mark.skipif(not client.fhir_available(), reason="IRIS FHIR is not reachable")

TEST_DATASET = "smoketest"


@pytest.fixture
def test_patient():
    """ONC-001 cloned as ONC-T001 with its own dataset tag, so the smoke test never touches seeded data."""
    raw = (dataset_dir("dev") / "pacienti" / "ONC-001.json").read_text(encoding="utf-8")
    patient = Patient.model_validate_json(raw.replace("ONC-001", "ONC-T001").replace('"sada": "dev"', '"sada": "smoketest"'))
    yield patient
    writers.flush()
    keys = client.tagged_keys("urn:meddi:dataset", TEST_DATASET)
    if keys:
        client.delete_entries(keys)
    writers._known_patients.pop(patient.patient_id, None)
    with client.sql_connection() as connection:
        connection.cursor().execute("DELETE FROM MEDDI.Triage_Result WHERE PatientId = ?", [patient.patient_id])


def triage_output(checkin_id: str, level: int, at: datetime) -> TriageOutput:
    return TriageOutput(
        checkin_id=checkin_id, patient_id="ONC-T001", uroven=level,
        doporuceny_krok="neodkladna_pomoc" if level == 4 else "kontaktovat_tym", upozornit_tym=True,
        doporuceny_kontakt="155 / urgentní příjem", klicove_nalezy=["Horečka G2 (pacient)"], varovne_priznaky=[],
        zduvodneni="test", doporuceni_pro_pacienta="Volejte ihned 155.", pravidla=["R-FEVER"], as_of=at)


def test_writers_round_trip(test_patient):
    checkin = next(item for item in test_patient.checkiny if item.checkin_id == "ONC-T001-C07")
    output = triage_output(checkin.checkin_id, 4, checkin.timestamp)
    writers.write_checkin(test_patient, checkin, output)
    first = QueueTask(id="ONC-T001-Q1", patient_id="ONC-T001", checkin_id=checkin.checkin_id, uroven=2, priority="routine",
                      owner="monitorovací centrum", why="první", created=checkin.timestamp - timedelta(hours=1))
    second = QueueTask(id="ONC-T001-Q2", patient_id="ONC-T001", checkin_id=checkin.checkin_id, uroven=4, priority="stat",
                       owner="sloužící lékař MOÚ", why="horečka", created=checkin.timestamp,
                       sla_do=checkin.timestamp + timedelta(minutes=15))
    writers.write_alert(first, None)
    writers.write_alert(second, output)
    writers.write_summary(DoctorSummary(
        patient_id="ONC-T001", as_of=checkin.timestamp, reason="eskalace", header="ONC-T001", proc_ted="horečka",
        lecba="AC", vyvoj="-", k_posouzeni="dnes", text="ONC-T001\nProč teď: horečka"))
    writers.write_chat("ONC-T001", {"id": "m1", "at": datetime.now(PRAGUE), "role": "user", "author": "pecujici",
                                    "text": "mamka má 38,4"})
    writers.write_chat("ONC-T001", {"id": "m2", "at": datetime.now(PRAGUE), "role": "navigator", "author": "navigator",
                                    "text": "Volejte ihned 155.", "level_card": {"uroven": 4}})
    writers.flush()

    assert client.get("Patient/ONC-T001")["identifier"][0]["value"] == "ONC-T001"
    checkin_resources = {"QuestionnaireResponse": 1, "Observation": 4, "Communication": 2, "RiskAssessment": 1}
    for resource_type, expected in checkin_resources.items():
        assert client.count(resource_type, {"identifier": "urn:meddi:checkin|ONC-T001-C07"}) == expected, resource_type
    risk = client.get("RiskAssessment/ONC-T001-C07-risk")
    assert risk["prediction"][0]["qualitativeRisk"]["coding"][0]["code"] == "4"
    assert client.get("Provenance/ONC-T001-C07-risk-prov")["agent"][0]["who"]["reference"] == "Device/meddi-navigator"

    open_tasks = client.search("Task", {"patient": "Patient/ONC-T001", "code": "urn:meddi:task|triage-alert"})
    assert len(open_tasks) == 1, "a second escalation must update the open Task, not duplicate it"
    assert open_tasks[0]["priority"] == "stat"
    assert {item["value"] for item in open_tasks[0]["identifier"] if item["system"] == "urn:meddi:task"} == {"ONC-T001-Q1", "ONC-T001-Q2"}
    assert client.get("Flag/ONC-T001-alert")["status"] == "active"

    assert client.count("Composition", {"patient": "Patient/ONC-T001"}) == 1
    reply = client.get("Communication/ONC-T001-chat-m2")
    assert reply["inResponseTo"] == [{"reference": "Communication/ONC-T001-chat-m1"}]
    assert client.get("Communication/ONC-T001-chat-m1")["sender"]["reference"] == "RelatedPerson/ONC-T001-pecujici"


def test_writers_never_raise_when_disabled(monkeypatch, test_patient):
    monkeypatch.setattr(client, "_available", (0.0, False))
    monkeypatch.setattr(client.settings, "fhir_base", "http://localhost:1/fhir/r4")
    monkeypatch.setattr(client, "_client", None)
    writers.write_chat("ONC-T001", {"id": "x", "role": "user", "text": "ahoj"})
    writers.flush()
    monkeypatch.undo()
    client._client = None
