"""Chronological replay (spec §12): each check-in is triaged with a context built strictly as of its own time."""
from collections.abc import Iterator

from app.context.builder import build_context
from app.models import Checkin, Patient, PatientContext, TriageOutput
from app.nlu import analyze
from app.triage.engine import triage


def replay(patients: list[Patient], use_llm: bool) -> Iterator[tuple[Checkin, PatientContext, TriageOutput]]:
    events = sorted(((checkin.timestamp, patient.patient_id, checkin, patient) for patient in patients for checkin in patient.checkiny),
                    key=lambda event: event[:2])
    for at, _, checkin, patient in events:
        ctx = build_context(patient, as_of=at)
        nlu = analyze(checkin, ctx, use_llm=use_llm)
        yield checkin, ctx, triage(checkin, ctx, nlu, use_llm=False)
