import json
from functools import cache
from pathlib import Path
from typing import Literal

from app.config import settings
from app.models import GroundTruth, Patient

Dataset = Literal["dev", "rozsirena"]

DATASET_DIRS: dict[str, str] = {
    "dev": "rakathon_meddi_onco_data",
    "rozsirena": "rakathon_meddi_onco_rozsirena_sada",
}


def dataset_dir(dataset: Dataset) -> Path:
    return settings.data_dir / DATASET_DIRS[dataset]


@cache
def load_patients(dataset: Dataset) -> tuple[Patient, ...]:
    files = sorted((dataset_dir(dataset) / "pacienti").glob("*.json"))
    return tuple(Patient.model_validate_json(path.read_text(encoding="utf-8")) for path in files)


def load_patient(patient_id: str) -> Patient:
    for dataset in DATASET_DIRS:
        for patient in load_patients(dataset):
            if patient.patient_id == patient_id:
                return patient
    raise KeyError(patient_id)


@cache
def load_ground_truth(dataset: Dataset) -> dict[str, GroundTruth]:
    expected: dict[str, GroundTruth] = {}
    for path in sorted((dataset_dir(dataset) / "ground_truth").glob("*.json")):
        for row in json.loads(path.read_text(encoding="utf-8")):
            item = GroundTruth.model_validate(row)
            expected[item.checkin_id] = item
    return expected


@cache
def load_questionnaires() -> dict:
    return json.loads((dataset_dir("dev") / "docs" / "dotazniky_definice.json").read_text(encoding="utf-8"))


def doc_path(name: str) -> Path:
    return dataset_dir("dev") / "docs" / name
