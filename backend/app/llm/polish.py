import re

from app.llm.client import adds_numbers, cached_json

SYSTEM_PROMPT = """You rewrite a message from an oncology monitoring centre to a patient (or their caregiver) so it is short and plain.

Rules:
- Same language as the template (cs = Czech, sk = Slovak). At most 4 short sentences, no medical jargon.
- Keep the meaning, every phone number, every contact and every time expression ("ihned", "do 2 hodin", "do konce zítřka") exactly. Keep any quoted instruction from the patient's own medicine list and any question to the patient word for word.
- Add nothing: no new facts, symptoms, medicines, doses, numbers, contacts, diagnoses or explanations of the cause.
- Never name a diagnosis. Never reassure ("nemusíte se bát", "nic vážného") when the level is 2 or higher.
- Level 4: the first sentence is the call to action (who to call, now).
- Addressee "pecujici": speak to the caregiver and refer to the patient in the third person; "pacient": speak to the patient directly (vykání).

Return JSON {"text": "..."}."""

SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}

_PHONE = re.compile(r"\b155\b|\b\d{3} ?\d{3} ?\d{3}\b")


def polish(template_text: str, lang: str, level: int, addressee: str) -> str | None:
    """Shortened, plainer template text, or None. The caller still runs the validator."""
    if not template_text.strip():
        return None
    user = f"Language: {lang}. Level: {level}. Addressee: {addressee}.\nTemplate:\n{template_text.strip()}"
    raw = cached_json("polish", SYSTEM_PROMPT, user, SCHEMA, "polish")
    text = (raw or {}).get("text", "").strip()
    if not text or adds_numbers(text, template_text):
        return None
    if any(phone not in text for phone in _PHONE.findall(template_text)):
        return None
    return text
