import re
from datetime import datetime

import pytest

from app.adapters.meddi_json import load_patient, load_patients, load_questionnaires
from app.fhir.client import compact
from app.fhir.mappers import (
    LAB_LOINC, alert_flag, alert_task, checkin_resources, composition, drug_classes, grade_observations,
    patient_resources, questionnaire_resources, risk_assessment,
)
from app.models import PRAGUE, DoctorSummary, QueueTask, TriageOutput

ID_PATTERN = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")
CHECKIN_TYPES = {"QuestionnaireResponse", "DocumentReference", "Task", "RiskAssessment", "Flag", "Composition",
                 "Provenance"}
ALL_PATIENTS = [patient for dataset in ("dev", "rozsirena") for patient in load_patients(dataset)]


def references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "reference":
                yield item
            else:
                yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def tags(resource):
    return {(tag["system"], tag["code"]) for tag in resource["meta"]["tag"]}


def output(**changes) -> TriageOutput:
    base = dict(
        checkin_id="ONC-001-C07", patient_id="ONC-001", uroven=4, doporuceny_krok="neodkladna_pomoc",
        upozornit_tym=True, doporuceny_kontakt="155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)",
        klicove_nalezy=["Horečka G2 (pacient)", "AC, C1 D10 (nadir)"], varovne_priznaky=["38,4 °C, zimnice"],
        zduvodneni="Horečka v nadiru.", doporuceni_pro_pacienta="Volejte ihned 724 590 848.",
        pravidla=["R-FEVER"], sla_do=datetime(2026, 9, 9, 22, 7, tzinfo=PRAGUE),
        as_of=datetime(2026, 9, 9, 21, 52, tzinfo=PRAGUE))
    return TriageOutput(**{**base, **changes})


@pytest.mark.parametrize("patient", ALL_PATIENTS, ids=lambda patient: patient.patient_id)
def test_patient_bundle_shape(patient):
    resources = [compact(resource) for resource in patient_resources(patient)]
    keys = [f"{resource['resourceType']}/{resource['id']}" for resource in resources]
    assert len(keys) == len(set(keys)), "duplicate ids in one bundle"
    assert all(ID_PATTERN.match(resource["id"]) for resource in resources)
    assert all({("urn:meddi:tag", "synthetic"), ("urn:meddi:dataset", patient.sada)} <= tags(resource)
               for resource in resources)
    assert not CHECKIN_TYPES & {resource["resourceType"] for resource in resources}, "seed must not hold check-ins"
    assert not any(resource["resourceType"] == "Communication" and "patient-message" in str(resource["category"])
                   for resource in resources)
    for reference in references(resources):
        assert reference in keys or reference == "Device/meddi-navigator", reference
    assert sum(resource["resourceType"] == "Patient" for resource in resources) == 1
    assert sum(resource["resourceType"] == "MedicationRequest" for resource in resources) == len(patient.leky)
    assert sum(resource["resourceType"] == "Observation" for resource in resources) == len(patient.laboratore) + 4


def test_patient_details():
    patient = load_patient("ONC-001")
    resources = {f"{resource['resourceType']}/{resource['id']}": resource for resource in patient_resources(patient)}
    fhir_patient = resources["Patient/ONC-001"]
    assert fhir_patient["identifier"] == [{"system": "urn:meddi:patient", "value": "ONC-001"}]
    assert fhir_patient["birthDate"] == "1978" and fhir_patient["gender"] == "female"
    assert fhir_patient["communication"][0]["language"]["coding"][0]["code"] == "cs"
    condition = resources["Condition/ONC-001-dx"]
    assert condition["code"]["coding"][0]["code"] == "C50.4" and condition["onsetDateTime"] == "2026-07-14"
    plan = resources["CarePlan/ONC-001-plan"]
    assert len(plan["activity"]) == len(patient.lecba.cykly)
    assert {"system": "urn:meddi:drug-class", "code": "cytotoxic"} in plan["meta"]["tag"]
    metoclopramide = next(resource for resource in resources.values()
                          if resource.get("medicationCodeableConcept", {}).get("text") == "Metoklopramid")
    assert metoclopramide["dosageInstruction"][0] == {"text": "10 mg, max 3× denně", "asNeededBoolean": True}
    assert metoclopramide["category"][0]["coding"][0]["code"] == "podpurny"
    leukocytes = resources["Observation/ONC-001-L01-leu"]
    assert leukocytes["code"]["coding"][0] == {"system": "http://loinc.org", "code": "6690-2", "display": "Leukocyty"}
    assert leukocytes["effectiveDateTime"] == "2026-08-31T09:30:00+02:00"
    assert leukocytes["interpretation"][0]["coding"][0]["code"] == "N"
    encounter = resources["Encounter/ONC-001-ev-1"]
    assert encounter["status"] == "finished" and encounter["period"]["end"] == "2026-09-13T14:00:00+02:00"
    assert resources["Communication/ONC-001-ev-3"]["category"][0]["coding"][0]["code"] == "aplikace_lecby"


def test_every_lab_code_has_loinc():
    assert {lab.kod for patient in ALL_PATIENTS for lab in patient.laboratore} <= set(LAB_LOINC)


def test_drug_classes():
    assert set(drug_classes("FOLFIRI + bevacizumab")) >= {"cytotoxic", "irinotecan", "fluoropyrimidine",
                                                           "antiangiogenic"}
    assert drug_classes("Morfin roztok (Oramorph)") == ["opioid"]
    assert drug_classes("Kapecitabin") == ["cytotoxic", "fluoropyrimidine"]
    assert drug_classes("Paracetamol") == []


def test_questionnaires_enable_when():
    questionnaires = questionnaire_resources(load_questionnaires())
    assert [questionnaire["id"] for questionnaire in questionnaires] == [
        "nezadouci-ucinky", "psychoonkologicky-screening", "bolest-analgeticka-terapie", "esas"]
    side_effects = {item["linkId"]: item for item in questionnaires[0]["item"]}
    assert len(side_effects) == 25
    for item in side_effects.values():
        for condition in item.get("enableWhen", []):
            source = side_effects[condition["question"]]
            codes = {option["valueCoding"]["code"] for option in source["answerOption"]}
            assert condition["answerCoding"]["code"] in codes
            assert condition["answerCoding"]["system"] == source["answerOption"][0]["valueCoding"]["system"]
    temperature = side_effects["teplota"]["answerOption"][1]
    assert temperature["extension"][0] == {"url": "urn:meddi:fhir:ext:answer-colour", "valueCode": "zluta"}
    assert side_effects["prujem"]["enableWhen"][0]["question"] == "stolice_typ"


def test_checkin_resources_fever():
    patient = load_patient("ONC-001")
    checkin = next(item for item in patient.checkiny if item.checkin_id == "ONC-001-C07")
    resources = {resource["resourceType"] + "/" + resource["id"]: compact(resource)
                 for resource in checkin_resources(patient, checkin)}
    response = resources["QuestionnaireResponse/ONC-001-C07-NU"]
    assert response["authored"] == "2026-09-09T21:52:00+02:00"
    assert response["author"] == {"reference": "Patient/ONC-001"}
    fever = next(item for item in response["item"] if item["linkId"] == "teplota")
    assert fever["answer"][0]["valueCoding"]["code"] == "1"
    assert {extension["url"].rsplit(":", 1)[1] for extension in fever["answer"][0]["extension"]} == {
        "answer-colour", "answer-warning"}
    effects = next(item for item in response["item"] if item["linkId"] == "ucinky")
    assert [answer["valueCoding"]["code"] for answer in effects["answer"]] == ["3", "5", "7", "11"]
    temperature = resources["Observation/ONC-001-C07-teplota-c"]
    assert temperature["code"]["coding"][0]["code"] == "8310-5" and temperature["valueQuantity"]["value"] == 38.4
    assert temperature["device"] == {"display": "domaci_teplomer"}
    pressure = resources["Observation/ONC-001-C07-bp"]
    assert [component["code"]["coding"][0]["code"] for component in pressure["component"]] == ["8480-6", "8462-4"]
    assert resources["Communication/ONC-001-C07-msg"]["payload"][0]["contentString"].startswith("Večer mi je zima")


def test_caregiver_and_missed_checkins():
    patient = load_patient("ONC-010")
    by_daughter = next(item for item in patient.checkiny if item.vyplnil == "dcera")
    resources = checkin_resources(patient, by_daughter)
    assert resources[0]["resourceType"] == "RelatedPerson" and resources[0]["id"] == "ONC-010-dcera"
    response = next(resource for resource in resources if resource["resourceType"] == "QuestionnaireResponse")
    assert response["author"]["reference"] == "RelatedPerson/ONC-010-dcera"
    missed = next(item for item in load_patient("ONC-017").checkiny if item.stav == "nevyplneno")
    [task] = checkin_resources(load_patient("ONC-017"), missed)
    assert task["resourceType"] == "Task" and task["code"]["coding"][0]["code"] == "missed-checkin"


def test_output_resources():
    risk = risk_assessment(output(), "dev", ["QuestionnaireResponse/ONC-001-C07-NU"])
    assert risk["prediction"][0]["qualitativeRisk"]["coding"][0]["code"] == "4"
    assert risk["method"]["text"] == "engine 0.1.0" and risk["note"] == [{"text": "Horečka v nadiru."}]
    assert risk["basis"] == [{"reference": "QuestionnaireResponse/ONC-001-C07-NU"}]
    [grade] = grade_observations(output(), "dev")
    assert grade["code"]["text"] == "Horečka G2 (pacient)" and grade["valueInteger"] == 2
    task = QueueTask(id="T-1", patient_id="ONC-001", checkin_id="ONC-001-C07", uroven=4, priority="stat",
                     owner="sloužící lékař MOÚ", why="horečka v nadiru", created=output().as_of,
                     sla_do=output().sla_do)
    fhir_task = alert_task(task, output(), "dev", "T-1")
    assert fhir_task["priority"] == "stat" and fhir_task["restriction"]["period"]["end"] == "2026-09-09T22:07:00+02:00"
    assert fhir_task["reasonReference"]["reference"] == "RiskAssessment/ONC-001-C07-risk"
    assert alert_flag(task, "dev", "T-1")["status"] == "active"
    summary = DoctorSummary(patient_id="ONC-001", as_of=output().as_of, reason="eskalace", header="ONC-001 · Jana K.",
                            proc_ted="Horečka 38,4 °C v nadiru.", lecba="AC C1", vyvoj="-", k_posouzeni="dnes",
                            text="ONC-001 · Jana K.\nProč teď: horečka")
    document = composition(summary, "dev")
    assert [section["title"] for section in document["section"]][:2] == ["Proč teď / K rozhodnutí", "Léčba"]
    assert "<br/>" in document["text"]["div"]


def test_compact_drops_empty_values():
    assert compact({"a": [], "b": {}, "c": None, "d": [{"e": ""}], "f": 0, "g": False}) == {"f": 0, "g": False}
