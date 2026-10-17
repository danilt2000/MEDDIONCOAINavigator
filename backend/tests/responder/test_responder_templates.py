import json
import re
import sys
import types

import pytest

from app.adapters.meddi_json import load_patient, load_patients, load_questionnaires
from app.agent.navigator import SYSTEM_PROMPT
from app.agent.patient_guide import PATIENT_TEXTS
from app.services.push import TEXTS
from app.triage.responder import T, WATCH, compose_reply
from app.triage.validator import normalize, sentences, validate_patient_text

CONTACTS = {
    1: [None],
    2: ["monitorovací centrum – vyřízení do konce následujícího pracovního dne", "monitorovací centrum – následující pracovní den"],
    3: ["telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h", "sloužící lékař MOÚ 724 590 848 – ihned"],
    4: ["155 / urgentní příjem", "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)"],
}
HINT_SETS = [
    [], ["R-FEVER"], ["O-DIARRHEA-RISK", "C-CONTRADICTION"], ["Y-IO-DIARRHEA"], ["R-VOMIT", "R-DEHYD"], ["Y-VOMIT"],
    ["O-BLEED-ANTICOAG"], ["R-BREATH"], ["O-PAIN"], ["Y-PAIN"], ["R-OPIOID"], ["O-PSYCH"], ["R-SUICIDE"], ["Y-BP"],
    ["O-HYPO"], ["R-ILEUS"], ["Y-CAREGIVER"], ["Y-GAP"], ["O-PAIN", "paliativni"], ["R-NEURO"],
]
FOLLOWUP = {"cs": "Píšete, že máte průjem asi 6× za den – je to tak?", "sk": "Píšete, že máte hnačku asi 6× za deň – je to tak?"}


def reply(patient_id: str, level: int, contact, addressee="pacient", hints=(), warning_signs=(), followup=None, lang=None):
    patient = load_patient(patient_id)
    lang = lang or patient.demografie.jazyk
    text = compose_reply(
        level, None, contact, lang, addressee, list(warning_signs), followup, list(hints), patient.leky, False,
        sex=patient.demografie.pohlavi, filled_by="dcera" if addressee == "pecujici" else None,
    )
    return text, validate_patient_text(text, level, lang, patient.leky, contact)


@pytest.mark.parametrize("level", [1, 2, 3, 4])
@pytest.mark.parametrize("lang", ["cs", "sk"])
@pytest.mark.parametrize("addressee", ["pacient", "pecujici"])
def test_every_template_passes_validator(level, lang, addressee):
    for patient_id in ("ONC-002", "ONC-014", "ONC-018", "ONC-013"):
        for contact in CONTACTS[level]:
            for hints in HINT_SETS:
                for followup in (None, FOLLOWUP[lang]):
                    text, problems = reply(patient_id, level, contact, addressee, hints, followup=followup, lang=lang)
                    assert problems == [], (patient_id, level, lang, addressee, contact, hints, text)
                    assert len(sentences(text)) <= 4


def test_every_dev_checkin_context_at_every_level():
    for patient in load_patients("dev"):
        addressees = {"pacient" if checkin.vyplnil == "pacient" else "pecujici" for checkin in patient.checkiny}
        for addressee in addressees:
            for level, contacts in CONTACTS.items():
                for contact in contacts:
                    text, problems = reply(patient.patient_id, level, contact, addressee)
                    assert problems == [], (patient.patient_id, level, addressee, text)


def test_level_4_starts_with_call_to_action_and_no_followup():
    text, _ = reply("ONC-018", 4, CONTACTS[4][1], followup=FOLLOWUP["sk"])
    assert text.startswith("Volajte ihneď 155")
    assert FOLLOWUP["sk"] not in text
    text, _ = reply("ONC-001", 4, CONTACTS[4][1], hints=["R-FEVER"])
    assert text.startswith("Volejte ihned 155 nebo sloužícího lékaře 724 590 848.")
    assert "Paralen neužívejte, dokud vás nevyšetří lékař." in text


def test_followup_comes_first():
    text, problems = reply("ONC-018", 3, CONTACTS[3][0], hints=["O-DIARRHEA-RISK", "C-CONTRADICTION"], followup=FOLLOWUP["sk"])
    assert problems == []
    assert text.startswith(FOLLOWUP["sk"])


def test_loperamide_scheme_quoted_verbatim():
    patient = load_patient("ONC-018")
    scheme = next(med.frekvence for med in patient.leky if med.lek == "Loperamid")
    text, problems = reply("ONC-018", 3, CONTACTS[3][0], hints=["O-DIARRHEA-RISK"])
    assert problems == []
    assert scheme in text


def test_no_loperamide_on_immunotherapy_diarrhoea():
    text, _ = reply("ONC-002", 2, CONTACTS[2][0], hints=["Y-IO-DIARRHEA"])
    assert "operamid" not in text


def test_caregiver_is_addressed_about_maminka():
    for level in (1, 2, 3, 4):
        text, problems = reply("ONC-014", level, CONTACTS[level][0], "pecujici", hints=["O-PAIN"] if level == 3 else [])
        assert problems == []
        assert "maminky" in text or "u ní" in text, text
    text, _ = reply("ONC-014", 3, CONTACTS[3][0], "pecujici", hints=["O-PAIN"])
    assert "nepodávejte další dávky" in text
    text, _ = reply("ONC-014", 4, CONTACTS[4][0], "pecujici", hints=["R-OPIOID"])
    assert "Další dávky léků na bolest teď nepodávejte." in text


def test_slovak_patient_gets_slovak_text():
    for level in (1, 2, 3, 4):
        text, problems = reply("ONC-018", level, CONTACTS[level][0])
        assert problems == []
        assert not any(char in text for char in "řůě")


def test_contact_and_time_named_for_levels_2_to_4():
    text, _ = reply("ONC-005", 2, CONTACTS[2][1])
    assert "monitorovacího centra" in text and "následující pracovní den" in text
    text, _ = reply("ONC-005", 3, CONTACTS[3][0])
    assert "s lékařem" in text and "do 2 hodin" in text
    text, _ = reply("ONC-005", 3, CONTACTS[3][1])
    assert "724 590 848" in text and "ihned" in text


def test_warning_sign_keywords_pick_topic_without_rule_ids():
    text, problems = reply("ONC-009", 3, CONTACTS[3][0], warning_signs=["TK ≥ 160/100 na antiangiogenní léčbě"])
    assert problems == []
    assert "180/110" in text


def _fake_polish(monkeypatch, result):
    module = types.ModuleType("app.llm.polish")
    module.polish = lambda text, lang, level, addressee: result(text)
    monkeypatch.setitem(sys.modules, "app.llm.polish", module)


def test_polish_used_only_when_valid(monkeypatch):
    patient = load_patient("ONC-005")
    contact = CONTACTS[2][0]
    template = compose_reply(2, "kontaktovat_tym", contact, "cs", "pacient", [], None, [], patient.leky, False)

    _fake_polish(monkeypatch, lambda text: "Předali jsme to týmu monitorovacího centra, ozve se vám do konce následujícího pracovního dne.")
    polished = compose_reply(2, "kontaktovat_tym", contact, "cs", "pacient", [], None, [], patient.leky, True)
    assert polished.startswith("Předali jsme")

    for bad in ("Nemusíte se bát, ozve se vám tým do konce následujícího pracovního dne.", "Může jít o sepsi, volejte 155 ihned.", None, ""):
        _fake_polish(monkeypatch, lambda text, bad=bad: bad)
        assert compose_reply(2, "kontaktovat_tym", contact, "cs", "pacient", [], None, [], patient.leky, True) == template

    def boom(text):
        raise RuntimeError("llm down")

    _fake_polish(monkeypatch, boom)
    assert compose_reply(2, "kontaktovat_tym", contact, "cs", "pacient", [], None, [], patient.leky, True) == template


def test_polish_must_keep_followup(monkeypatch):
    patient = load_patient("ONC-018")
    contact = CONTACTS[3][0]
    _fake_polish(monkeypatch, lambda text: "Ešte dnes vám zavolá lekár MOÚ, do 2 hodín.")
    text = compose_reply(3, "telekonzultace", contact, "sk", "pacient", [], FOLLOWUP["sk"], ["O-DIARRHEA-RISK"], patient.leky, True)
    assert normalize(text).startswith(normalize(FOLLOWUP["sk"]))


def test_engine_patient_hint_quoted_and_mapped_back_to_rule():
    hint_sk = "horúčka, krv v stolici, závraty alebo hnačka 7× za deň"
    text, problems = reply("ONC-018", 3, CONTACTS[3][0], hints=["C-CONTRADICTION"], warning_signs=[hint_sk])
    assert problems == []
    assert hint_sk in text
    assert "loperamid" in text


def test_clinician_label_never_quoted_to_patient():
    label = "4–6 stolic nad normál při imunoterapii, fluoropyrimidinech nebo irinotekanu; průjem nereagující na loperamid"
    text, problems = reply("ONC-002", 3, CONTACTS[3][0], hints=["O-DIARRHEA-RISK"], warning_signs=[label])
    assert problems == []
    assert "fluoropyrimid" not in text and "imunoterap" not in text


def test_second_person_hint_not_used_for_caregiver():
    hint = "nemočíte déle než 10 hodin, točí se vám hlava nebo omdlíte"
    text, problems = reply("ONC-014", 3, CONTACTS[3][0], "pecujici", hints=["R-DEHYD"], warning_signs=[hint])
    assert problems == []
    assert hint not in text and "u ní" in text


def test_patient_facing_texts_never_name_the_institution():
    texts = json.dumps([T, WATCH, TEXTS, PATIENT_TEXTS, SYSTEM_PROMPT, load_questionnaires()], ensure_ascii=False)
    assert not re.search(r"MOÚ|\bMOU\b|Masaryk", texts)
