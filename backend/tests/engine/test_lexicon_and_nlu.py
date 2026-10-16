import pytest
from engine_helpers import WEDNESDAY_EVENING, checkin, context

from app.models import Fact, NluResult
from app.nlu import analyze, analyze_text
from app.nlu.lexicon_cs_sk import lexicon_facts
from app.triage.engine import triage, triage_chat


def facts(text: str, author: str = "pacient") -> dict:
    found, _ = lexicon_facts(text, "zprava", author)
    return {fact.type: fact.value for fact in found}


@pytest.mark.parametrize("text, fact_type, value", [
    ("naměřila jsem 38,4", "temperature_c", 38.4),
    ("Zimnice, 38,6, kolem portu je kůže zarudlá", "temperature_c", 38.6),
    ("od vcera mam hnacku asi 6 krat", "stool_count_above_normal", 6),
    ("Od včera řidší stolice, asi 3× navíc.", "stool_count_above_normal", 3),
    ("Zvracela sem dvakrat", "vomiting_episodes_24h", 2),
    ("V noci 7x zvracela.", "vomiting_episodes_24h", 7),
    ("V noci musím spát na dvou polštářích", "orthopnea", True),
    ("Mamka je od včera hodně spavá, skoro nereaguje", "drowsiness_new", True),
    ("Krvacal som z nosa asi 5 minut", "nosebleed_minutes", 5),
    ("Mamka 4 dny bez stolice.", "constipation_days", 4),
    ("Tablety jsem pár dní vynechala", "missed_medication", True),
    ("pripadam si k nicemu nema cenu se snazit", "hopelessness", True),
])
def test_lexicon_extracts(text, fact_type, value):
    assert facts(text).get(fact_type) == value


@pytest.mark.parametrize("text, fact_type", [
    ("Průjem, ale bez krve.", "blood_in_stool"),
    ("Teplotu nemám.", "fever_reported"),
    ("Bolest na hrudi nemám.", "chest_pain_new"),
    ("Pořád nic, břicho nafouklé, ale plyny odcházejí, nezvracím.", "no_stool_no_gas"),
    ("Pořád nic, břicho nafouklé, ale plyny odcházejí, nezvracím.", "vomiting_episodes_24h"),
    ("Já už nevím, jak to zvládat, nespím.", "caregiver_strain"),
    ("foto_ruce.jpg – několik hematomů na předloktí", "colicky_pain"),
])
def test_lexicon_negations_and_scope(text, fact_type):
    assert fact_type not in facts(text)


def test_caregiver_strain_only_from_a_relative():
    assert facts("Já už nevím, jak to zvládat, nespím.", author="dcera").get("caregiver_strain") is True


def test_quotes_are_verbatim():
    text = "Večer mi je zima, třesu se, naměřila jsem 38,4. Mám si vzít Paralen?"
    found, _ = lexicon_facts(text)
    assert found and all(fact.quote in text for fact in found)


def test_llm_facts_never_lower_the_level(monkeypatch):
    """Union semantics: LLM facts and negations can only keep or raise the level."""
    item = checkin(message="Dnes mi není dobře, mám průjem 3x.")
    ctx = context(["fluoropyrimidine"])
    base = triage(item, ctx, analyze(item, ctx, use_llm=False), use_llm=False).uroven
    fake = NluResult(facts=[Fact(type="stool_count_above_normal", value=5, quote="průjem 3x")], negations=["blood_in_stool"])
    monkeypatch.setattr("app.nlu._llm", lambda texts, lang, author: fake)
    raised = triage(item, ctx, analyze(item, ctx, use_llm=True), use_llm=False).uroven
    assert base == 1 and raised == 3


def test_unconfirmed_llm_drowsiness_asks_instead_of_red(monkeypatch):
    item = checkin(message="Mamka spí většinu dne, bolesti drží morfin.", filled_by="dcera")
    ctx = context(["opioid"])
    fake = NluResult(facts=[Fact(type="drowsiness_new", value=True, quote="spí většinu dne")])
    monkeypatch.setattr("app.nlu._llm", lambda texts, lang, author: fake)
    output = triage(item, ctx, analyze(item, ctx, use_llm=True), use_llm=False)
    assert output.uroven == 2 and output.doplnujici_otazka


def test_chat_message_escalates_like_a_checkin():
    ctx = context(chemo=True, nadir=True, at=WEDNESDAY_EVENING)
    nlu = analyze_text("mam 38,4 a trese me zima", ctx, "pacient", use_llm=False)
    assert {fact.type for fact in nlu.facts} >= {"temperature_c", "chills"}
    output = triage_chat("T-001", "mam 38,4 a trese me zima", "pacient", ctx, nlu, WEDNESDAY_EVENING, use_llm=False)
    assert output.uroven == 4 and output.zdroj == "chat"
    assert output.doporuceny_kontakt == "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)"
    assert any(evidence.zdroj == "chat" for evidence in output.dukazy)


def test_chat_question_without_symptoms_stays_green():
    ctx = context(at=WEDNESDAY_EVENING)
    text = "Kdy mám další kontrolu?"
    output = triage_chat("T-001", text, "pecujici", ctx, analyze_text(text, ctx, "pecujici", use_llm=False), WEDNESDAY_EVENING, use_llm=False)
    assert output.uroven == 1 and output.adresat == "pecujici"
