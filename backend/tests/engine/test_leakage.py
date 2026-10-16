"""Replay leakage guards (spec §12): nothing dated after as_of reaches the context or the engine."""
import inspect

import pytest

from app.adapters.meddi_json import load_patients
from app.context import builder
from app.triage import engine


@pytest.mark.parametrize("dataset", ["dev", "rozsirena"])
def test_no_resource_after_as_of(dataset):
    patients = load_patients(dataset)
    if dataset == "rozsirena":
        patients = patients[::10]
    for patient in patients:
        for checkin in patient.checkiny:
            ctx = builder.build_context(patient, checkin.timestamp)
            assert all(lab.timestamp <= ctx.as_of for lab in ctx.labs)
            assert all(event.timestamp <= ctx.as_of for event in ctx.team_events)
            assert all(item.timestamp <= ctx.as_of for item in ctx.recent_checkins)
            assert all(exam.datum < ctx.as_of.date() for exam in ctx.exams)
            assert len(ctx.recent_checkins) <= 10


def test_future_hospitalisation_is_invisible():
    patient = next(item for item in load_patients("dev") if item.patient_id == "ONC-001")
    fever = next(item for item in patient.checkiny if item.checkin_id == "ONC-001-C07")
    ctx = builder.build_context(patient, fever.timestamp)
    assert not any(event.typ == "hospitalizace" for event in ctx.team_events)
    assert not any(lab.cas == "23:40" for lab in ctx.labs)


def test_exam_from_the_same_day_is_invisible():
    patient = next(item for item in load_patients("dev") if item.patient_id == "ONC-007")
    same_day = next(item for item in patient.checkiny if item.checkin_id == "ONC-007-C08")
    later = next(item for item in patient.checkiny if item.checkin_id == "ONC-007-C09")
    assert all("44 %" not in exam.vysledek for exam in builder.build_context(patient, same_day.timestamp).exams)
    assert any("44 %" in exam.vysledek for exam in builder.build_context(patient, later.timestamp).exams)


def test_engine_never_reads_scenario_or_ground_truth():
    sources = inspect.getsource(engine) + inspect.getsource(builder)
    for forbidden in ("nazev_scenare", "vychazi_ze_scenare", "ground_truth", "Eval_Expected"):
        assert forbidden not in sources
