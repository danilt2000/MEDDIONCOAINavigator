from datetime import datetime

from app.models import PRAGUE, Answer, Checkin, Lek, Measurement, PatientContext, QuestionnaireFill, TriageOutput
from app.nlu import analyze
from app.triage.engine import triage

WEDNESDAY_EVENING = datetime(2026, 9, 9, 21, 52, tzinfo=PRAGUE)
THURSDAY_MORNING = datetime(2026, 9, 10, 10, 15, tzinfo=PRAGUE)


SCALES = {"uzkost", "depresivita", "zvladani", "nrs", "sos", "pohoda", "bolest", "unava", "ospalost", "nevolnost", "nechutenstvi",
          "dusnost", "deprese", "jiny"}


def fill(form: str, answers: dict) -> QuestionnaireFill:
    """Ints are option indexes (raw values for scale items outside the side-effect form); strings are free text."""
    items = []
    for qid, value in answers.items():
        if isinstance(value, str) or (form != "nezadouci_ucinky" and qid in SCALES):
            items.append(Answer(otazka_id=qid, otazka=qid, odpoved=value, odpoved_index=None, barva=None, upozorneni=None))
        else:
            items.append(Answer(otazka_id=qid, otazka=qid, odpoved=str(value), odpoved_index=value, barva=None, upozorneni=None))
    return QuestionnaireFill(vyplneni_id=f"{form}-1", dotaznik_id=form, dotaznik_nazev=form, odpovedi=items, nejvyssi_barva=None)


def checkin(answers: dict | None = None, vitals: dict | None = None, message: str | None = None, at: datetime = THURSDAY_MORNING,
            forms: dict | None = None, filled_by: str = "pacient", checkin_id: str = "T-001-C01", status: str = "vyplneno",
            attachments: list[str] | None = None) -> Checkin:
    fills = [fill("nezadouci_ucinky", answers or {"pocit": 1, "sobestacnost": 0})] if status == "vyplneno" else []
    fills += [fill(form, items) for form, items in (forms or {}).items()]
    return Checkin(
        checkin_id=checkin_id, patient_id="T-001", datum=at.date(), cas=at.strftime("%H:%M"), den_sledovani=10, stav=status,
        vyplnil=filled_by, dotazniky=fills, zprava_pacienta=message, prilohy=attachments or [],
        vitalni_funkce={key: Measurement(hodnota=value, zdroj="test") for key, value in (vitals or {}).items()} or None,
    )


def context(classes: list[str] | None = None, chemo: bool = False, nadir: bool = False, at: datetime = THURSDAY_MORNING,
            comorbidities: list[str] | None = None, meds: list[Lek] | None = None, baselines: dict | None = None,
            recent: list[Checkin] | None = None, team_events=None, diagnosis: str = "Karcinom", intent: str = "kurativní",
            directive: str | None = None, lang: str = "cs") -> PatientContext:
    return PatientContext(
        patient_id="T-001", as_of=at, age=60, sex="F", lang=lang, filled_by_default="pacient", diagnosis=diagnosis,
        regimen="testovací režim", intent=intent, cycle=1 if chemo else None, cycle_day=10 if nadir else (4 if chemo else None),
        in_nadir=nadir, chemo_window=chemo, drug_classes=sorted(set(classes or []) | ({"cytotoxic"} if chemo else set())),
        meds=meds or [], comorbidities=comorbidities or [], advance_directive=directive, recent_checkins=recent or [],
        team_events=team_events or [], baselines={"ecog": 0.0, "weight": 70.0, **(baselines or {})},
    )


def run(item: Checkin, ctx: PatientContext) -> TriageOutput:
    return triage(item, ctx, analyze(item, ctx, use_llm=False), use_llm=False)


def level(item: Checkin, ctx: PatientContext) -> int:
    return run(item, ctx).uroven
