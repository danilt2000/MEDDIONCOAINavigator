from app.llm.client import adds_numbers, cached_json
from app.models import SummaryFact

SYSTEM_PROMPT = """You write the body of a 30-second summary for an oncologist at Masarykův onkologický ústav, in Czech (or the language given), from a list of facts only.

Format, one line each, skip a line if no fact supports it:
Proč teď: one sentence, what matters now and what is expected from the doctor.
Léčba: regimen, cycle, relevant medicines and prior results.
Vývoj: the trend as a dated series ("3. 9. 83,4 kg → 7. 9. 85,0 kg"), not every value.
Laboratoř: only abnormal or relevant results.
Nehlásí: important symptoms the patient denies.
K posouzení lékařem: what the doctor should assess, phrased as "k posouzení" / "možná ...".

Rules:
- Use only the given facts. Every number and date you write must appear in the facts. Nothing else, no outside knowledge.
- Mark sources in brackets as given: (pacient), (pečující), (naměřeno), (odhad systému).
- No diagnosis as a certainty, no treatment or dose proposal.
- At most 120 words.

Return JSON {"text": "..."} with the lines separated by newlines, without the header."""

SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def _fact_line(fact: SummaryFact) -> str:
    date = f"{fact.datum}: " if fact.datum else ""
    return f"- {date}{fact.text} ({fact.zdroj})"


def write_summary(facts: list[SummaryFact], header: str, lang: str = "cs") -> str | None:
    """Header + LLM-written body from the facts only, or None. The caller checks numbers and dates."""
    if not facts:
        return None
    fact_lines = "\n".join(_fact_line(fact) for fact in facts)
    user = f"Language: {lang}.\nHeader: {header}\nFacts:\n{fact_lines}"
    raw = cached_json("summary", SYSTEM_PROMPT, user, SCHEMA, "doctor_summary")
    body = (raw or {}).get("text", "").strip()
    if not body or adds_numbers(body, f"{header}\n{fact_lines}"):
        return None
    return f"{header}\n{body}"
