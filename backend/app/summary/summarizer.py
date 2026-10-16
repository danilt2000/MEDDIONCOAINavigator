import logging
import re
from datetime import date

from app.models import DoctorSummary, Patient, PatientContext, SummaryFact, TriageOutput
from app.summary import facts as collect
from app.triage.validator import DIAGNOSIS, normalize

log = logging.getLogger(__name__)

MAX_WORDS = 120
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
DATE = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.(?:\s?\d{4})?|\b(\d{4})-(\d{2})-(\d{2})\b")
PROPOSAL = re.compile(
    r"\b(?:doporucuj\w*|navrhuj\w*|zvys\w* davk\w*|sniz\w* davk\w*|vysad\w*|nasad\w*|prerus\w*|zmen\w* lecb\w*"
    r"|uprav\w* davk\w*|podejte|podat\w*|zahaj\w*|ukonc\w*)"
)
INTERPRETATION = re.compile(
    r"\b(?:souvislost\w*|retenc\w*|pricin\w*|zpusoben\w*|pravdepodobn\w*|svedc\w*|podezren\w*|diagnoz\w*|kvuli)"
)
# (section, facts it keeps at least), dropped from the end in this order while over the word limit
TRIM_ORDER = [("vyvoj", 2), ("lecba", 1), ("laborator", 0), ("vyvoj", 1), ("nehlasi", 0), ("k_posouzeni", 1), ("proc_ted", 1)]


def word_count(text: str) -> int:
    return sum(1 for token in text.split() if any(char.isalnum() for char in token))


def _labels(reason: str, lab_day: str | None) -> dict[str, str]:
    application = collect.REASONS.get(normalize(reason or "")) == "souhrn před aplikací"
    return {
        "proc_ted": "K rozhodnutí dnes" if application else "Proč teď",
        "lecba": "Léčba",
        "vyvoj": "Vývoj",
        "laborator": f"Laboratoř {lab_day}" if lab_day else "Laboratoř",
        "nehlasi": "Nehlásí",
        "k_posouzeni": "K posouzení lékařem",
    }


def _section_text(name: str, items: list[SummaryFact]) -> str:
    joined = (". " if name == "proc_ted" else "; ").join(item.text for item in items)
    return joined if joined.endswith((".", "…")) else joined + "."


def _render(header: str, sections: dict[str, list[SummaryFact]], labels: dict[str, str]) -> str:
    lines = [header] + [f"{labels[name]}: {_section_text(name, items)}" for name, items in sections.items() if items]
    return "\n".join(lines)


def _fit(header: str, sections: dict[str, list[SummaryFact]], labels: dict[str, str]) -> str:
    text = _render(header, sections, labels)
    while word_count(text) > MAX_WORDS:
        name = next((name for name, minimum in TRIM_ORDER if len(sections[name]) > minimum), None)
        if name is None:
            break
        sections[name].pop()
        text = _render(header, sections, labels)
    return text


def _numbers(text: str) -> set[float]:
    return {float(token.replace(",", ".")) for token in NUMBER.findall(text)}


def _dates(text: str) -> set[tuple[int, int]]:
    found = set()
    for match in DATE.finditer(text):
        if match.group(1):
            found.add((int(match.group(1)), int(match.group(2))))
        else:
            found.add((int(match.group(5)), int(match.group(4))))
    return found


def check_llm_text(text: str, facts: list[SummaryFact], header: str, denied: list[tuple[str, ...]] = ()) -> list[str]:
    """Every number and date must exist in the facts; no new diagnosis, interpretation or treatment proposal;
    nothing the patient denies may appear as reported; the section layout stays."""
    source = " ".join([header, *(fact.text for fact in facts)])
    allowed_dates = _dates(source) | {
        (day.day, day.month) for day in (date.fromisoformat(fact.datum[:10]) for fact in facts if fact.datum)
    }
    problems = [f"unknown_date: {day}. {month}." for day, month in _dates(text) - allowed_dates]
    allowed = _numbers(DATE.sub(" ", source))
    problems += [
        f"unknown_number: {token}" for token in NUMBER.findall(DATE.sub(" ", text)) if float(token.replace(",", ".")) not in allowed
    ]
    norm_source = normalize(source)
    norm_text = normalize(text)
    problems += [f"diagnosis: {match.group(0)}" for match in DIAGNOSIS.finditer(norm_text) if match.group(0) not in norm_source]
    problems += [f"proposal: {match.group(0)}" for match in PROPOSAL.finditer(norm_text) if match.group(0) not in norm_source]
    problems += [f"interpretation: {match.group(0)}" for match in INTERPRETATION.finditer(norm_text) if match.group(0) not in norm_source]
    lines = [normalize(line) for line in text.splitlines()[1:] if line.strip()]
    if any(re.fullmatch(r"[^:]{1,40}:\s*", line) for line in lines):
        problems.append("empty_section")
    if not any(line.startswith(("proc ted", "k rozhodnuti")) for line in lines):
        problems.append("missing_proc_ted")
    if not any(line.startswith("k posouzeni") for line in lines):
        problems.append("missing_k_posouzeni")
    for stems in denied:
        if any(stem in line for line in lines if not line.startswith("nehlasi") for stem in stems):
            problems.append(f"denied_symptom_reported: {stems[0]}")
    if word_count(text) > MAX_WORDS:
        problems.append(f"too_long: {word_count(text)} words")
    return problems


def _llm_text(all_facts: list[SummaryFact], header: str, denied: list[tuple[str, ...]]) -> str | None:
    try:
        from app.llm.summary_writer import write_summary

        text = write_summary(all_facts, header, "cs")
    except Exception:
        log.exception("summary writer failed")
        return None
    if not text:
        return None
    text = text.strip()
    if not text.startswith(header):
        text = f"{header}\n{text}"
    problems = check_llm_text(text, all_facts, header, denied)
    if problems:
        log.warning("LLM summary rejected, deterministic text used: %s", problems)
        return None
    return text


def _denied(sections: dict[str, list[SummaryFact]]) -> list[tuple[str, ...]]:
    denied_text = " ".join(fact.text for fact in sections["nehlasi"])
    others = normalize(" ".join(fact.text for name, items in sections.items() if name != "nehlasi" for fact in items))
    return [
        stems for _, label, stems in collect.RED_FLAGS
        if label in denied_text and not any(stem in others for stem in stems)
    ]


def build_summary(
    patient: Patient, ctx: PatientContext, outputs: list[TriageOutput], reason: str, use_llm: bool = False
) -> DoctorSummary:
    as_of = collect.aware(ctx.as_of)
    visible = collect.visible_outputs(outputs, patient.patient_id, as_of)
    latest = visible[-1] if visible else None
    checkins = collect.window_checkins(ctx, as_of)
    cycle, cycle_day = collect.current_cycle(patient, ctx, as_of)
    header = collect.header(patient, as_of, reason, cycle)
    lab_day, lab_facts = collect.laborator(ctx, as_of)
    sections = {
        "proc_ted": collect.proc_ted(latest, ctx, checkins),
        "lecba": collect.lecba(patient, ctx, cycle, cycle_day, checkins, as_of),
        "vyvoj": collect.vyvoj(ctx, visible, latest, checkins, as_of)
        or [SummaryFact(text="bez výrazných změn za posledních 14 dní", zdroj="odhad systému")],
        "laborator": lab_facts,
        "nehlasi": collect.nehlasi(latest, checkins, as_of),
        "k_posouzeni": collect.k_posouzeni(latest, ctx, reason, cycle),
    }
    labels = _labels(reason, lab_day)
    text = _fit(header, sections, labels)
    kept = [fact for items in sections.values() for fact in items]
    llm_text = _llm_text(kept, header, _denied(sections)) if use_llm else None
    return DoctorSummary(
        patient_id=patient.patient_id,
        as_of=as_of,
        reason=reason,
        header=header,
        proc_ted=_section_text("proc_ted", sections["proc_ted"]),
        lecba=_section_text("lecba", sections["lecba"]),
        vyvoj=_section_text("vyvoj", sections["vyvoj"]),
        laborator=(f"{lab_day} – " if lab_day else "") + _section_text("laborator", sections["laborator"]) if sections["laborator"] else None,
        nehlasi=_section_text("nehlasi", sections["nehlasi"]) if sections["nehlasi"] else None,
        k_posouzeni=_section_text("k_posouzeni", sections["k_posouzeni"]),
        facts=kept,
        text=llm_text or text,
        generated_by="llm" if llm_text else "template",
    )
