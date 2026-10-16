import json
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import settings
from app.llm import client
from app.llm.polish import polish
from app.llm.summary_writer import write_summary
from app.models import Checkin, SummaryFact
from app.nlu import llm_extractor
from app.nlu.llm_extractor import SCHEMA, extract_llm, find_quote, texts_for_checkin, to_result

TEXTS = [("zprava", "od vcera mam hnacku asi 6 krat, slaby som"), ("dotaznik", "Z nosa, asi 5 minút, potom prestalo.")]
RAW = {
    "lang": "sk",
    "facts": [
        {"type": "stool_count_above_normal", "value": "6", "period_h": 24, "certainty": "approx", "quote": "od včera mám hnačku asi 6 krát"},
        {"type": "nosebleed_minutes", "value": 5, "period_h": None, "certainty": "approx", "quote": "asi 5 minut"},
        {"type": "temperature_c", "value": 38.5, "period_h": None, "certainty": "exact", "quote": "teplota 38,5"},
        {"type": "made_up_type", "value": True, "period_h": None, "certainty": "exact", "quote": "slaby som"},
    ],
    "negations": [{"type": "blood_in_stool", "quote": "bez krve"}, {"type": "weakness", "quote": "slaby som"}],
    "patient_questions": ["Mám si vziať loperamid?", "potom prestalo"],
}


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "cache_dir", tmp_path)
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    return tmp_path


def fake_complete(responses: list):
    calls = []

    def complete_json(system, user, schema, name, **options):
        calls.append(user)
        return responses.pop(0), {"prompt_tokens": 100, "completion_tokens": 20}

    return complete_json, calls


def test_find_quote_ignores_diacritics_case_and_spacing_and_returns_original_span():
    assert find_quote("Od včera  mám HNAČKU", TEXTS) == ("zprava", "od vcera mam hnacku")
    assert find_quote("asi 5 minut.", TEXTS) == ("dotaznik", "asi 5 minút")
    assert find_quote("hnacka 6 krat", TEXTS) is None
    assert find_quote("  ", TEXTS) is None


def test_to_result_keeps_only_quoted_known_facts():
    result = to_result(RAW, TEXTS, "cs", "pacient")
    assert result.lang == "sk"
    assert [(fact.type, fact.value, fact.source) for fact in result.facts] == [
        ("stool_count_above_normal", 6.0, "zprava"),
        ("nosebleed_minutes", 5, "dotaznik"),
    ]
    assert result.facts[0].quote == "od vcera mam hnacku asi 6 krat"
    assert result.negations == ["weakness"]
    assert result.patient_questions == ["potom prestalo"]
    assert result.caregiver_strain is False


def test_to_result_caregiver_strain_needs_a_quoted_fact():
    texts = [("zprava", "Já už nevím, jak to zvládat, nespím.")]
    raw = {"lang": "xx", "facts": [{"type": "caregiver_strain", "value": True, "period_h": None, "certainty": "exact", "quote": "ja uz nevim, jak to zvladat"}]}
    result = to_result(raw, texts, "cs", "dcera")
    assert result.caregiver_strain and result.lang == "cs" and result.author == "dcera"
    raw["facts"][0]["quote"] = "jsem vyčerpaná"
    assert to_result(raw, texts, "cs", "dcera").caregiver_strain is False


def test_extract_llm_caches_and_replays_without_network(cache_dir, monkeypatch):
    complete_json, calls = fake_complete([RAW])
    monkeypatch.setattr(client, "complete_json", complete_json)
    first = extract_llm(TEXTS, "sk", "pacient")
    assert len(calls) == 1 and len(list((cache_dir / "nlu").glob("*.json"))) == 1

    def no_network(*args, **kwargs):
        raise AssertionError("cache hit must not call the LLM")

    monkeypatch.setattr(client, "complete_json", no_network)
    monkeypatch.setattr(settings, "llm_enabled", False)
    assert extract_llm(TEXTS, "sk", "pacient") == first
    assert extract_llm(TEXTS, "sk", "dcera") is None


def test_extract_llm_key_depends_on_inputs_and_role_not_on_relative(cache_dir, monkeypatch):
    complete_json, calls = fake_complete([RAW, RAW, RAW])
    monkeypatch.setattr(client, "complete_json", complete_json)
    extract_llm(TEXTS, "sk", "dcera")
    extract_llm(TEXTS, "sk", "syn")
    extract_llm(TEXTS, "cs", "dcera")
    extract_llm(TEXTS[:1], "cs", "dcera")
    assert len(calls) == 3


def test_extract_llm_empty_texts_and_failures(cache_dir, monkeypatch):
    assert extract_llm([("zprava", "  ")], "sk", "pacient").facts == []
    monkeypatch.setattr(client, "complete_json", lambda *args, **kwargs: None)
    assert extract_llm(TEXTS, "sk", "pacient") is None
    assert not list(cache_dir.glob("**/*.json"))


def test_extract_llm_pseudonymises_before_sending(cache_dir, monkeypatch):
    complete_json, calls = fake_complete([{"lang": "cs", "facts": [], "negations": [], "patient_questions": []}])
    monkeypatch.setattr(client, "complete_json", complete_json)
    extract_llm([("chat", "Narozena 3.4.1950, RČ 505403/1234, mail jana@example.cz")], "cs", "pacient")
    assert "1950" not in calls[0] and "505403" not in calls[0] and "jana@" not in calls[0]


def test_texts_for_checkin_uses_message_attachments_and_free_text_answers():
    checkin = Checkin.model_validate({
        "checkin_id": "X-C01", "patient_id": "X", "datum": "2026-09-01", "cas": "08:00", "den_sledovani": 1,
        "stav": "vyplneno", "vyplnil": "pacient", "zprava_pacienta": " Krvácel jsem z nosu. ",
        "prilohy": ["foto.jpg – modřiny"],
        "dotazniky": [{"vyplneni_id": "V1", "dotaznik_id": "nezadouci_ucinky", "dotaznik_nazev": "NU", "nejvyssi_barva": None, "odpovedi": [
            {"otazka_id": "krvaceni", "otazka": "Krvácení?", "odpoved": "Ano", "odpoved_index": 1, "barva": "zluta", "upozorneni": None},
            {"otazka_id": "krvaceni_popis", "otazka": "Odkud?", "odpoved": "Z nosu 10 minut", "odpoved_index": None, "barva": None, "upozorneni": None},
            {"otazka_id": "nrs", "otazka": "NRS", "odpoved": 3, "odpoved_index": None, "barva": None, "upozorneni": None},
        ]}],
    })
    assert texts_for_checkin(checkin) == [
        ("zprava", "Krvácel jsem z nosu."), ("priloha", "foto.jpg – modřiny"), ("dotaznik", "Z nosu 10 minut"),
    ]


def assert_strict(schema):
    if schema.get("type") == "object":
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        for child in schema["properties"].values():
            assert_strict(child)
    if schema.get("type") == "array":
        assert_strict(schema["items"])
    for option in schema.get("anyOf", []):
        assert_strict(option)


def test_schemas_are_valid_for_strict_structured_output():
    from app.llm import polish as polish_module, summary_writer

    for schema in (SCHEMA, polish_module.SCHEMA, summary_writer.SCHEMA):
        assert_strict(schema)
    assert set(SCHEMA["properties"]["facts"]["items"]["properties"]["type"]["enum"]) == set(llm_extractor.FACT_TYPES)
    assert len(llm_extractor.FACT_TYPES) == 50


class FakeCompletions:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        content, finish_reason = outcome
        message = SimpleNamespace(content=content)
        usage = SimpleNamespace(model_dump=lambda **kwargs: {"prompt_tokens": 1})
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)], usage=usage)


def use_fake_openai(monkeypatch, outcomes):
    completions = FakeCompletions(outcomes)
    monkeypatch.setattr(client, "get_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=completions)))
    return completions


def test_complete_json_parses_structured_output_and_falls_back_without_reasoning_effort(monkeypatch):
    rejected = openai.BadRequestError(
        "Unsupported parameter: 'reasoning_effort'",
        response=httpx.Response(400, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")),
        body=None,
    )
    completions = use_fake_openai(monkeypatch, [rejected, (json.dumps({"text": "ok"}), "stop")])
    assert client.complete_json("s", "u", {"type": "object"}, "t") == ({"text": "ok"}, {"prompt_tokens": 1})
    assert "reasoning_effort" in completions.requests[0] and "reasoning_effort" not in completions.requests[1]
    assert completions.requests[1]["response_format"]["json_schema"]["strict"] is True
    assert "temperature" not in completions.requests[1]


@pytest.mark.parametrize("outcome", [("{\"text\": \"cut", "length"), ("not json", "stop"), (None, "stop"), RuntimeError("down")])
def test_complete_json_returns_none_on_bad_output(monkeypatch, outcome):
    use_fake_openai(monkeypatch, [outcome])
    assert client.complete_json("s", "u", {"type": "object"}, "t") is None


def test_numbers_are_compared_canonically():
    assert client.numbers("3. 9. 85,0 kg, 09") == {"3", "9", "85"}
    assert not client.adds_numbers("3. 9. 85 kg", "2026-09-03 85.0 kg")
    assert client.adds_numbers("86,4 kg", "85,0 kg")


def test_polish_rejects_new_numbers_and_dropped_phones(cache_dir, monkeypatch):
    template = "Volejte ihned 155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848). Nečekejte do rána."
    good = "Volejte ihned 155, případně lékaře MOÚ 724 590 848. Nečekejte do rána."
    complete_json, _ = fake_complete([
        {"text": "Volejte ihned 155. Nečekejte."},
        {"text": "Volejte ihned 155 nebo 724 590 848, vezměte 2 tablety."},
        {"text": good},
    ])
    monkeypatch.setattr(client, "complete_json", complete_json)
    assert polish(template, "cs", 4, "pacient") is None
    assert polish(template, "cs", 4, "pecujici") is None
    assert polish(template, "sk", 4, "pacient") == good
    assert polish("", "cs", 1, "pacient") is None


def test_write_summary_prepends_header_and_rejects_invented_numbers(cache_dir, monkeypatch):
    facts = [SummaryFact(text="váha 85,0 kg", datum="2026-09-07", zdroj="naměřeno"),
             SummaryFact(text="spí na dvou polštářích", datum="2026-09-10", zdroj="pacient")]
    complete_json, _ = fake_complete([{"text": "Vývoj: 7. 9. 85 kg → 10. 9. ortopnoe (pacient)."}, {"text": "Vývoj: 86,4 kg."}])
    monkeypatch.setattr(client, "complete_json", complete_json)
    assert write_summary(facts, "ONC-007 · Hana D., 55 let") == "ONC-007 · Hana D., 55 let\nVývoj: 7. 9. 85 kg → 10. 9. ortopnoe (pacient)."
    assert write_summary(facts, "ONC-007 · Hana D., 55 let", "sk") is None
    assert write_summary([], "x") is None
