import argparse
import re
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.llm.client import cache_stats, cached_json
from app.models import Checkin, Fact, NluResult

CACHE_KIND = "nlu"
SOURCES = ("zprava", "priloha", "dotaznik", "chat")

NUMERIC_TYPES = {
    "temperature_c", "stool_count_above_normal", "vomiting_episodes_24h", "no_urine_hours", "nosebleed_minutes",
    "abdominal_pain_nrs", "pain_nrs", "rescue_doses_per_day", "weight_change_kg",
}
FACT_TYPES = [
    "temperature_c", "chills", "stool_count_above_normal", "blood_in_stool", "black_stool", "vomiting_episodes_24h",
    "cannot_keep_fluids", "no_urine_hours", "fainting", "dizziness_standing", "dyspnea_rest", "dyspnea_exertion",
    "orthopnea", "chest_pain_new", "palpitations", "confusion", "drowsiness_new", "breathing_slow", "seizure",
    "limb_weakness_new", "speech_problem", "bleeding_site", "nosebleed_minutes", "head_injury", "bruises_new",
    "abdominal_pain_nrs", "colicky_pain", "no_stool_no_gas", "headache_severe", "vision_problem", "thirst_polyuria",
    "weight_change_kg", "edema", "calf_swelling_one_side", "pain_nrs", "rescue_doses_per_day", "liquids_only",
    "weakness", "suicidal_thoughts", "suicide_plan_intent_means", "hopelessness", "missed_medication",
    "caregiver_strain", "port_redness", "nail_fold_inflammation", "skin_blisters", "tinnitus",
    "neuropathy_function_loss", "cough_new", "other",
]

SYSTEM_PROMPT = """You extract clinical facts from home check-in texts of oncology patients (Czech or Slovak, often with typos and without diacritics). You never diagnose and never judge severity; you only record what the text states.

Return JSON:
- lang: "cs" or "sk", the language the texts are written in. Diacritics-free text that is valid in both languages -> use the profile language given in the input.
- facts: things the author states as present now or within the last days. One fact per finding:
  - type: one of the allowed types below; anything clinically relevant that fits none -> "other".
  - value: a number for numeric types (null if the text gives no number, never guess one); for bleeding_site the site in Czech ("nos", "dásně", "moč", "stolice", "zvratky", "rána", ...); for edema the place and time ("kotníky večer"); for missed_medication the medicine name; for breathing_slow the breaths per minute if stated; for port_redness the size in cm if stated; for "other" a short Czech label ("návaly horka", "svědění kůže"); otherwise true.
  - period_h: hours the statement covers if the text says so ("od včera" -> 24, "v noci" -> 12, "dnes" -> 24), else null.
  - certainty: "exact", "approx" (asi, cca, možná, kolem) or "uncertain" (the author is unsure the finding is real).
  - quote: the shortest exact span copied character for character from ONE input text that supports the fact. Do not fix typos, do not add diacritics, do not translate, do not join pieces of different texts.
- negations: findings the author explicitly denies ("teplotu nemám", "nezvracím", "vidím normálně", "plyny odcházejí"), each as {type, quote} with the same allowed types.
- patient_questions: sentences in which the author asks something (usually ending with "?"), each copied exactly from the text. Never symptoms or form answers.

Rules:
- Only what is written. Hypotheticals, fears and plans ("bojím se zvracení", "kdyby měla horečku") are not facts. Symptoms that are fully gone ("konečně se ulevilo") are not facts; a symptom that is better but still there is a fact with its current value.
- Facts are symptoms, complaints, measurements and self-care problems. Not facts: treatment status, appointments, cycle numbers, medicines taken as prescribed, "cítím se líp", "jinak dobrý".
- Pain with a number -> pain_nrs (abdominal pain -> abdominal_pain_nrs); pain without a number -> the same type with value null. headache_severe only for a strong headache; a mild headache -> other "bolest hlavy".
- Counts: stools above the usual number per day -> stool_count_above_normal ("hnačka 6x" -> 6, "3× navíc" -> 3); vomiting episodes -> vomiting_episodes_24h. Temperatures like "38,4" -> temperature_c 38.4; temperature_c only when the text names a body temperature, fever ("teplota", "horečka", "°C") or a number between 35 and 42; "horečka" without a number -> value null. Text without a clear subject ("zase vysoký") -> other with those words. No urine "od včera večer" / "celou noc" -> no_urine_hours 12 approx, "od včera" -> 24 approx; "málo močím" is not no_urine_hours (use other "málo močí").
- A relative or caregiver may write about the patient ("mamka", "taťka", "píše dcera"): facts about the patient are facts. caregiver_strain only when the writer describes their own exhaustion or inability to cope ("už nevím, jak to zvládat", "nespím").
- Breathlessness at rest -> dyspnea_rest, on effort -> dyspnea_exertion, when lying flat (needs pillows or sitting up to breathe) -> orthopnea. Dizziness on standing up -> dizziness_standing, other dizziness -> other "závratě". New drowsiness, hardly reacting or hard to wake -> drowsiness_new; slow breathing -> breathing_slow; disorientation or not making sense -> confusion; slurred or garbled speech, cannot find words -> speech_problem (talking little or being withdrawn is other "nemluví").
- Red-flag types (chest_pain_new, dyspnea_rest, fainting, confusion, seizure, limb_weakness_new, speech_problem, blood_in_stool, black_stool, head_injury, suicide_plan_intent_means) only when the text clearly says so.
- Thoughts of not wanting to live or of death -> suicidal_thoughts; a stated plan, intent or means -> suicide_plan_intent_means; "nemá to cenu", "jsem k ničemu" -> hopelessness.
- Skipped or reduced medicines by the patient's own decision -> missed_medication.
- Photo descriptions ("foto_x.jpg – ...") are texts like any other. "None" inside a text (e.g. "bolest – None") means an empty form field, not a denial.

Allowed types: """ + ", ".join(FACT_TYPES) + "."

_TYPE_ENUM = {"type": "string", "enum": FACT_TYPES}
SCHEMA = {
    "type": "object",
    "properties": {
        "lang": {"type": "string", "enum": ["cs", "sk"]},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": _TYPE_ENUM,
                    "value": {"anyOf": [{"type": "number"}, {"type": "string"}, {"type": "boolean"}, {"type": "null"}]},
                    "period_h": {"anyOf": [{"type": "number"}, {"type": "null"}]},
                    "certainty": {"type": "string", "enum": ["exact", "approx", "uncertain"]},
                    "quote": {"type": "string"},
                },
                "required": ["type", "value", "period_h", "certainty", "quote"],
                "additionalProperties": False,
            },
        },
        "negations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"type": _TYPE_ENUM, "quote": {"type": "string"}},
                "required": ["type", "quote"],
                "additionalProperties": False,
            },
        },
        "patient_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["lang", "facts", "negations", "patient_questions"],
    "additionalProperties": False,
}

_BIRTH_NUMBER = re.compile(r"\b\d{6}\s?/\s?\d{3,4}\b")
_BIRTH_DATE = re.compile(r"\b\d{1,2}\.\s?\d{1,2}\.\s?19\d{2}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def pseudonymise(text: str) -> str:
    text = _BIRTH_NUMBER.sub("[RČ]", text)
    text = _BIRTH_DATE.sub("[datum]", text)
    return _EMAIL.sub("[email]", text)


def texts_for_checkin(checkin: Checkin) -> list[tuple[str, str]]:
    """The free texts of a check-in, exactly as app.nlu.analyze passes them to extract_llm."""
    texts: list[tuple[str, str]] = []
    if checkin.zprava_pacienta and checkin.zprava_pacienta.strip():
        texts.append(("zprava", checkin.zprava_pacienta.strip()))
    texts += [("priloha", note.strip()) for note in checkin.prilohy if note and note.strip()]
    for fill in checkin.dotazniky:
        for answer in fill.odpovedi:
            if answer.odpoved_index is None and isinstance(answer.odpoved, str) and answer.odpoved.strip():
                texts.append(("dotaznik", answer.odpoved.strip()))
    return texts


def author_role(author: str) -> str:
    return "pacient" if author in ("pacient", "patient", "") else "pecujici"


def _fold(text: str) -> tuple[str, list[int]]:
    """Lower-case, diacritics-free, single-spaced text plus the index of each folded char in the original."""
    folded: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        for part in unicodedata.normalize("NFKD", char).casefold():
            if unicodedata.combining(part):
                continue
            if part.isspace():
                if not folded or folded[-1] == " ":
                    continue
                part = " "
            folded.append(part)
            origin.append(index)
    return "".join(folded), origin


def find_quote(quote: str, texts: list[tuple[str, str]]) -> tuple[str, str] | None:
    """(source, verbatim span of the original text) when quote is a diacritics-insensitive substring of a text."""
    needle, _ = _fold(quote.strip(" \t\n.,;:!?\"'„“”‚‘’()-–"))
    if not needle:
        return None
    for source, text in texts:
        haystack, origin = _fold(text)
        start = haystack.find(needle)
        if start >= 0:
            return source, text[origin[start]: origin[start + len(needle) - 1] + 1]
    return None


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return None


def _user_message(texts: list[tuple[str, str]], lang_hint: str, author: str) -> str:
    lines = [f"Profile language: {lang_hint}. Written by: {author_role(author)}.", "Texts:"]
    lines += [f"[{source}] {text}" for source, text in texts]
    return "\n".join(lines)


def to_result(raw: dict, texts: list[tuple[str, str]], lang_hint: str, author: str) -> NluResult:
    facts: list[Fact] = []
    seen: set[tuple] = set()
    for item in raw.get("facts") or []:
        if not isinstance(item, dict) or item.get("type") not in FACT_TYPES:
            continue
        match = find_quote(str(item.get("quote") or ""), texts)
        if match is None:
            continue
        source, quote = match
        value = _number(item.get("value")) if item["type"] in NUMERIC_TYPES else item.get("value")
        key = (item["type"], str(value), quote)
        if key in seen:
            continue
        seen.add(key)
        facts.append(Fact(
            type=item["type"], value=value, period_h=_number(item.get("period_h")),
            certainty=item.get("certainty"), quote=quote, source=source if source in SOURCES else "zprava",
        ))
    negations = []
    for item in raw.get("negations") or []:
        if isinstance(item, dict) and item.get("type") in FACT_TYPES and find_quote(str(item.get("quote") or ""), texts):
            if item["type"] not in negations:
                negations.append(item["type"])
    questions = []
    for question in raw.get("patient_questions") or []:
        match = find_quote(str(question), texts)
        if match and match[1] not in questions:
            questions.append(match[1])
    lang = raw.get("lang") if raw.get("lang") in ("cs", "sk") else lang_hint
    return NluResult(
        lang=lang, author=author, facts=facts, negations=negations, patient_questions=questions,
        caregiver_strain=any(fact.type == "caregiver_strain" for fact in facts),
    )


def extract_llm(texts: list[tuple[str, str]], lang_hint: str, author: str) -> NluResult | None:
    """LLM fact extraction (spec §8.7). None when the LLM is off or fails and nothing is cached."""
    lang_hint = lang_hint if lang_hint in ("cs", "sk") else "cs"
    texts = [(source, pseudonymise(text.strip())) for source, text in texts if text and text.strip()]
    if not texts:
        return NluResult(lang=lang_hint, author=author)
    raw = cached_json(CACHE_KIND, SYSTEM_PROMPT, _user_message(texts, lang_hint, author), SCHEMA, "nlu_facts")
    if raw is None:
        return None
    return to_result(raw, texts, lang_hint, author)


def _precompute(datasets: list[str], workers: int) -> None:
    from app.adapters.meddi_json import load_patients

    jobs = []
    for dataset in datasets:
        for patient in load_patients(dataset):
            for checkin in patient.checkiny:
                texts = texts_for_checkin(checkin)
                if checkin.stav == "vyplneno" and texts:
                    jobs.append((checkin.checkin_id, texts, patient.demografie.jazyk, checkin.vyplnil))
    print(f"{len(jobs)} check-ins with free text in {', '.join(datasets)}; {workers} workers", flush=True)
    started = time.time()
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_llm, texts, lang, author): checkin_id for checkin_id, texts, lang, author in jobs}
        for done, future in enumerate(as_completed(futures), 1):
            if future.result() is None:
                failed.append(futures[future])
            if done % 25 == 0 or done == len(jobs):
                print(f"  {done}/{len(jobs)}  failed {len(failed)}  {time.time() - started:.0f}s", flush=True)
    if failed:
        print("failed (re-run to retry):", " ".join(sorted(failed)))
    print("cache:", cache_stats(CACHE_KIND))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.nlu.llm_extractor")
    parser.add_argument("--precompute", choices=["all", "dev", "rozsirena"], required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    datasets = ["dev", "rozsirena"] if args.precompute == "all" else [args.precompute]
    _precompute(datasets, max(1, min(args.workers, 8)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
