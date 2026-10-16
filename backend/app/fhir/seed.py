"""Seed IRIS FHIR with the MEDDI packages (spec §12): Questionnaires + one transaction Bundle per patient, no check-ins.

    python -m app.fhir.seed --datasets dev,rozsirena [--reset] [--no-sql]
"""

import argparse
import time
from collections import Counter

from app.adapters.meddi_json import load_patients, load_questionnaires
from app.fhir import client
from app.fhir.mappers import navigator_device, patient_resources, questionnaire_resources

RESOURCE_TYPES = [
    "Patient", "RelatedPerson", "Condition", "AllergyIntolerance", "Consent", "Observation", "CarePlan",
    "MedicationRequest", "DiagnosticReport", "Encounter", "Communication", "Questionnaire", "QuestionnaireResponse",
    "DocumentReference", "Task", "RiskAssessment", "Flag", "Composition", "Provenance", "Device",
]
DELETE_BATCH = 200


def dataset_tag(dataset: str) -> str:
    return f"urn:meddi:dataset|{dataset}"


def reset(datasets: list[str]) -> None:
    for dataset in datasets:
        keys = client.tagged_keys("urn:meddi:dataset", dataset)
        for start in range(0, len(keys), DELETE_BATCH):
            client.delete_entries(keys[start:start + DELETE_BATCH])
        print(f"reset {dataset}: deleted {len(keys)} resources", flush=True)


def counts(datasets: list[str]) -> dict[str, Counter]:
    return {dataset: Counter({resource_type: client.count(resource_type, {"_tag": dataset_tag(dataset)})
                              for resource_type in RESOURCE_TYPES}) for dataset in datasets}


def seed(datasets: list[str], reset_first: bool = False, load_sql: bool = True) -> dict[str, Counter]:
    started = time.monotonic()
    if reset_first:
        reset(datasets)
    client.transaction([navigator_device(), *questionnaire_resources(load_questionnaires())])
    print("Questionnaires ×4 + Device MEDDI navigátor", flush=True)
    for dataset in datasets:
        patients = load_patients(dataset)
        written = 0
        for index, patient in enumerate(patients, 1):
            resources = patient_resources(patient)
            client.transaction(resources)
            written += len(resources)
            print(f"[{dataset} {index}/{len(patients)}] {patient.patient_id}: {len(resources)} resources", flush=True)
        print(f"{dataset}: {len(patients)} patients, {written} resources", flush=True)
    if load_sql:
        try:
            from app.fhir.sql_tables import load_tables
            load_tables()
        except Exception as error:  # SQL tables are a bonus; FHIR seed is the contract
            print(f"SQL tables skipped: {error}")
    result = counts(datasets)
    for dataset, by_type in result.items():
        print(f"FHIR {dataset}: " + ", ".join(f"{name} {total}" for name, total in by_type.items() if total))
    print(f"done in {time.monotonic() - started:.0f} s")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--datasets", default="dev,rozsirena")
    parser.add_argument("--reset", action="store_true", help="delete resources tagged with the datasets first")
    parser.add_argument("--no-sql", action="store_true", help="skip the MEDDI.* SQL tables")
    args = parser.parse_args()
    seed([name.strip() for name in args.datasets.split(",") if name.strip()], args.reset, not args.no_sql)


if __name__ == "__main__":
    main()
