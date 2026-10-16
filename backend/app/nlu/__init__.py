"""NLU = lexicon safety net ∪ LLM extractor (spec §8.7). A red flag found by either counts."""
from app.models import Checkin, Fact, NluResult, PatientContext
from app.nlu.lexicon_cs_sk import lexicon_facts, questions


def checkin_texts(checkin: Checkin) -> list[tuple[str, str]]:
    try:
        from app.nlu.llm_extractor import texts_for_checkin
        return texts_for_checkin(checkin)
    except ImportError:
        texts = [("zprava", checkin.zprava_pacienta.strip())] if checkin.zprava_pacienta and checkin.zprava_pacienta.strip() else []
        texts += [("priloha", note.strip()) for note in checkin.prilohy if note and note.strip()]
        for fill in checkin.dotazniky:
            for answer in fill.odpovedi:
                if answer.odpoved_index is None and isinstance(answer.odpoved, str) and answer.odpoved.strip():
                    texts.append(("dotaznik", answer.odpoved.strip()))
        return texts


def _llm(texts: list[tuple[str, str]], lang: str, author: str) -> NluResult | None:
    try:
        from app.nlu.llm_extractor import extract_llm
        return extract_llm(texts, lang, author)
    except Exception:
        return None


def analyze_texts(texts: list[tuple[str, str]], ctx: PatientContext, author: str, use_llm: bool = True) -> NluResult:
    facts: list[Fact] = []
    negations: list[str] = []
    patient_questions: list[str] = []
    for source, text in texts:
        found, negated = lexicon_facts(text, source, author)
        facts += found
        negations += [item for item in negated if item not in negations]
        patient_questions += questions(text)
    lang = ctx.lang
    llm = _llm(texts, ctx.lang, author) if use_llm and texts else None
    if llm is not None:
        seen = {(fact.type, fact.quote) for fact in facts}
        facts += [fact for fact in llm.facts if (fact.type, fact.quote) not in seen]
        negations += [item for item in llm.negations if item not in negations]
        patient_questions += [item for item in llm.patient_questions if item not in patient_questions]
        lang = llm.lang
    return NluResult(
        lang=lang, author=author, facts=facts, negations=negations, patient_questions=patient_questions,
        caregiver_strain=any(fact.type == "caregiver_strain" for fact in facts),
    )


def analyze(checkin: Checkin, ctx: PatientContext, use_llm: bool = True) -> NluResult:
    return analyze_texts(checkin_texts(checkin), ctx, checkin.vyplnil, use_llm)


def analyze_text(text: str, ctx: PatientContext, author: str, use_llm: bool = True) -> NluResult:
    return analyze_texts([("chat", text.strip())] if text and text.strip() else [], ctx, author, use_llm)
