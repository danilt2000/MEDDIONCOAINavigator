"""Thin bridges from the API to the engine modules (imported lazily)."""

from datetime import date, datetime
from typing import Iterator

from app.config import settings
from app.models import Checkin, DoctorSummary, NluResult, Patient, PatientContext, TriageOutput


def _cycle_at(patient: Patient, day: date) -> tuple[int | None, int | None]:
    started = [cycle for cycle in patient.lecba.cykly if cycle.datum_d1 <= day]
    if not started:
        return None, None
    current = max(started, key=lambda cycle: cycle.datum_d1)
    return current.cyklus, (day - current.datum_d1).days + 1


def build_context(patient: Patient, as_of: datetime, extra_checkins: list[Checkin] | None = None) -> PatientContext:
    from app.context.builder import build_context as engine_build_context

    return engine_build_context(patient, as_of, extra_checkins=extra_checkins or [])


def analyze(checkin: Checkin, ctx: PatientContext, use_llm: bool) -> NluResult:
    from app.nlu import analyze as engine_analyze

    return engine_analyze(checkin, ctx, use_llm=use_llm)


def triage(checkin: Checkin, ctx: PatientContext, nlu: NluResult, use_llm: bool) -> TriageOutput:
    from app.triage.engine import triage as engine_triage

    return engine_triage(checkin, ctx, nlu, use_llm=use_llm)


def run_checkin(patient: Patient, checkin: Checkin, extra_checkins: list[Checkin], use_llm: bool) -> tuple[PatientContext, NluResult, TriageOutput]:
    ctx = build_context(patient, checkin.timestamp, extra_checkins)
    nlu = analyze(checkin, ctx, use_llm)
    return ctx, nlu, triage(checkin, ctx, nlu, use_llm)


def replay(patients: list[Patient], use_llm: bool) -> Iterator[tuple[Checkin, PatientContext, TriageOutput]]:
    from app.eval.replay import replay as engine_replay

    return engine_replay(patients, use_llm)


def build_summary(patient: Patient, ctx: PatientContext, outputs: list[TriageOutput], reason: str) -> DoctorSummary:
    from app.summary.summarizer import build_summary as engine_build_summary

    return engine_build_summary(patient, ctx, outputs, reason, use_llm=False)


def use_llm_default() -> bool:
    return settings.llm_enabled and bool(settings.openai_api_key)
