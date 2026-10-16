from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.meddi_json import load_patient, load_patients
from app.api import mock_meddi
from app.config import settings
from app.interop import alerts, hl7


def fields(message: str, segment: str) -> list[str]:
    return next(line.split("|") for line in message.split("\r") if line.startswith(segment + "|"))


def test_oru_message_matches_the_sda_path_requirements():
    patient = load_patient("ONC-001")
    messages = hl7.patient_messages(patient)
    first = messages["ONC-001-L01"]
    assert list(messages) == sorted({lab.odber_id for lab in patient.laboratore})
    assert fields(first, "MSH")[8:12] == ["ORU^R01^ORU_R01", "ONC-001-L01", "P", "2.5.1"]
    assert fields(first, "MSH")[17] == "UNICODE UTF-8"
    assert fields(first, "PID")[3] == "ONC-001^^^MEDDI^MR"
    assert fields(first, "PID")[5] == "K^Jana"
    assert fields(first, "ORC")[29] == "LAB"
    assert fields(first, "OBR")[7] == "20260831093000+0200"
    assert "OBX|1|NM|6690-2^Leukocytes [#/volume] in Blood by Automated count^LN||6.3|10*9/L|4-10|N|||F" in first
    assert first.count("\rOBX|") == sum(lab.odber_id == "ONC-001-L01" for lab in patient.laboratore)


def test_every_lab_code_in_both_datasets_has_a_loinc():
    codes = {lab.kod for dataset in ("dev", "rozsirena") for patient in load_patients(dataset) for lab in patient.laboratore}
    assert codes <= hl7.LOINC.keys()


def test_escape_and_units():
    assert hl7.escape("a|b^c&d~e\\f") == "a\\F\\b\\S\\c\\T\\d\\R\\e\\E\\f"
    assert [hl7.ucum(unit) for unit in ("10^9/l", "µmol/l", "g/l", "")] == ["10*9/L", "umol/L", "g/L", ""]


def test_mock_meddi_stores_and_lists():
    app = FastAPI()
    app.include_router(mock_meddi.router)
    client = TestClient(app)
    mock_meddi.received.clear()
    created = client.post("/mock/meddi/requests", json={"patient_id": "ONC-001", "uroven": 4, "why": "Horečka"})
    assert created.status_code == 201
    listed = client.get("/mock/meddi/requests").json()
    assert [item["payload"]["why"] for item in listed] == ["Horečka"]
    assert listed[0]["received_at"]


def test_send_alert_returns_false_when_iris_is_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "iris_port", 1999)
    assert alerts.send_alert_via_iris({"patient_id": "ONC-001", "uroven": 2}) is False
