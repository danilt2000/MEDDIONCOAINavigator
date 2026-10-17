import asyncio
from datetime import datetime

import pytest

from app import store
from app.adapters.meddi_json import load_patient
from app.agent import navigator
from app.config import settings
from app.models import PRAGUE, Measurement
from app.services import engine


def at(*parts):
    return datetime(*parts, tzinfo=PRAGUE)


def chat(patient_id, text, when):
    return asyncio.run(navigator.chat_turn(patient_id, text, "pacient", None, when))


def close_open_tasks():
    for task in store.list_tasks():
        if task.status != "completed":
            store.apply_task_action(task.id, "close", None, "test")
    navigator._pending.clear()
    navigator._resolved.clear()


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", False)
    monkeypatch.setattr("app.services.side_effects.dispatch_alert", lambda *args, **kwargs: None)
    close_open_tasks()
    yield
    close_open_tasks()


def test_chat_cannot_withdraw_an_open_red_instruction():
    assert chat("ONC-001", "mam 38,4 a trese me zima", at(2026, 9, 9, 21, 52)).triage.uroven == 4
    for text, minute in (("už je mi dobře, zrušte to", 55), ("Mám si vzít Paralen a počkat do rána?", 57)):
        reply = chat("ONC-001", text, at(2026, 9, 9, 21, minute))
        assert reply.level_card.uroven == 4
        assert "155" in reply.reply_text
        assert "Paralen neužívejte" in reply.reply_text


def test_numeric_answer_corrects_only_the_count_it_was_asked_about():
    patient = load_patient("ONC-018")
    base = next(checkin for checkin in patient.checkiny if checkin.checkin_id == "ONC-018-C03")
    when = at(2026, 9, 11, 9, 0)
    checkin = base.model_copy(update={"checkin_id": "ONC-018-T01", "datum": when.date(), "cas": "09:00",
                                      "zprava_pacienta": "od vcera mam hnacku asi 6 krat a teplotu 38,5"})
    _ctx, nlu, output = engine.run_checkin(patient, checkin, [], False)
    assert output.uroven == 4 and "C-CONTRADICTION" in output.pravidla
    store.record_output(checkin, output, live=True, nlu=nlu)
    store.raise_task(output, side_effects=False)
    reply = chat("ONC-018", "nie, len 3 krat", at(2026, 9, 11, 9, 10))
    assert reply.triage.uroven == 4 and "R-FEVER" in reply.triage.pravidla


def test_followup_text_keeps_unrelated_numbers():
    text, answered = navigator._followup_text(("zvracela jsem 4x a teplota 38,2", "Píšete, že jste zvracel(a) 4× za den – je to tak?", 4), "ne, jen 2x")
    assert "38,2" in text and "4x" not in text and "4×" not in text and answered


def test_number_about_something_else_does_not_answer_the_count_question():
    pending = ("od vcera mam hnacku asi 6x", "Píšete, že máte hnačku asi 6× za deň – je to tak?", 3)
    for answer in ("mam horucku 38,6", "teplota mam 37,2", "tlak mam 185/115 a silno ma boli hlava"):
        text, answered = navigator._followup_text(pending, answer)
        assert "6x" in text and not answered, answer
    text, answered = navigator._followup_text(pending, "nie, dnes len 2 krat")
    assert "6x" not in text and answered
    text, _answered = navigator._followup_text(("mám 38,5", "Píšete o teplotě 38,5 °C – je to tak?", 3), "ne, měla jsem 37,2")
    assert "38,5" not in text


VERIFY_CS = "Je spavost výrazně větší než obvykle, nebo nejde probudit?"
VERIFY_SK = "Je spavosť výrazne väčšia ako obvykle, alebo sa nedá prebudiť?"


def test_verify_question_is_not_triaged_as_the_patients_words():
    for earlier, question, answer in (("Bojím se, že je maminka po morfinu nějak ospalá.", VERIFY_CS, "ne"),
                                      ("som dnes nejaky ospaly", VERIFY_SK, "nie, je to ako obvykle, len som unaveny"),
                                      ("Manželka je dnes nějak ospalá.", VERIFY_CS, "ne, je normálně spavá jako vždycky po chemoterapii")):
        text, answered = navigator._followup_text((earlier, question, 2), answer)
        assert question not in text and answered
    text, _answered = navigator._followup_text(("Manželka je dnes nějak ospalá.", VERIFY_CS, 2), "ano")
    assert VERIFY_CS in text


def asked(patient_id, text, question, author, lang, when):
    asyncio.run(navigator.chat_turn(patient_id, text, author, lang, when))
    navigator._pending[patient_id] = (text, question, 2)


def test_no_to_the_verify_question_is_not_red_and_yes_still_is():
    when = at(2026, 9, 9, 21, 52)
    asked("ONC-014", "Bojím se, že je maminka po morfinu nějak ospalá.", VERIFY_CS, "pecujici", None, when)
    reply = asyncio.run(navigator.chat_turn("ONC-014", "ne", "pecujici", None, when))
    assert reply.triage.uroven < 4 and not {"R-OPIOID", "R-NEURO"} & set(reply.triage.pravidla), reply.triage.pravidla
    asked("ONC-018", "som dnes nejaky ospaly", VERIFY_SK, "pacient", "sk", when)
    reply = asyncio.run(navigator.chat_turn("ONC-018", "nie, je to ako obvykle, len som unaveny", "pacient", "sk", when))
    assert reply.triage.uroven < 4 and not {"R-OPIOID", "R-NEURO"} & set(reply.triage.pravidla), reply.triage.pravidla
    asked("ONC-014", "Bojím se, že je maminka po morfinu nějak ospalá.", VERIFY_CS, "pecujici", None, when)
    assert asyncio.run(navigator.chat_turn("ONC-014", "ano", "pecujici", None, when)).triage.uroven == 4


def record_checkin(checkin_id, when, message, vitals=None):
    patient = load_patient("ONC-018")
    base = next(checkin for checkin in patient.checkiny if checkin.checkin_id == "ONC-018-C03")
    checkin = base.model_copy(update={"checkin_id": checkin_id, "datum": when.date(), "cas": when.strftime("%H:%M"),
                                      "zprava_pacienta": message, "vitalni_funkce": vitals or {}})
    _ctx, nlu, output = engine.run_checkin(patient, checkin, [], False)
    store.record_output(checkin, output, live=True, nlu=nlu)
    store.raise_task(output, side_effects=False)
    return output


def contradiction_checkin(monkeypatch, vitals=None):
    output = record_checkin("ONC-018-T02", at(2026, 9, 11, 9, 0), "od vcera mam hnacku asi 6 krat", vitals)
    assert output.uroven == (4 if vitals else 3) and "C-CONTRADICTION" in output.pravidla
    navigator.clear_history("ONC-018")

    def say(text, minute):
        when = at(2026, 9, 11, 9, minute)
        monkeypatch.setattr(store, "get_now", lambda: when)
        return asyncio.run(navigator.chat_turn("ONC-018", text, "pacient", None, when))

    return say


def test_unrelated_first_message_keeps_the_unanswered_contradiction(monkeypatch):
    say = contradiction_checkin(monkeypatch)
    reply = say("teplota mam 37,2", 10)
    assert reply.triage.uroven == 3 and "O-DIARRHEA-RISK" in reply.triage.pravidla


def test_answered_contradiction_is_not_floored_back_on_the_next_message(monkeypatch):
    say = contradiction_checkin(monkeypatch)
    assert say("nie, dnes len 2 krat", 10).triage.uroven == 2
    reply = say("Mozem normalne jest a pit?", 12)
    assert reply.triage.uroven < 3 and "NAV-OPEN-EPISODE" not in reply.triage.pravidla
    assert say("mam horucku 38,6", 14).triage.uroven == 4
    reply = say("Mozem normalne jest a pit?", 16)
    assert reply.triage.uroven == 4 and "NAV-OPEN-EPISODE" in reply.triage.pravidla


def test_answer_does_not_release_a_fever_from_the_checkin_form(monkeypatch):
    say = contradiction_checkin(monkeypatch, {"teplota_c": Measurement(hodnota=38.6, zdroj="pacient")})
    for text, minute in (("nie, dnes len 2 krat", 10), ("Mozem normalne jest a pit?", 12)):
        reply = say(text, minute)
        assert reply.triage.uroven == 4 and "NAV-OPEN-EPISODE" in reply.triage.pravidla, text


def test_new_checkin_after_a_resolved_contradiction_is_floored_again(monkeypatch):
    say = contradiction_checkin(monkeypatch)
    assert say("nie, dnes len 2 krat", 10).triage.uroven == 2
    assert record_checkin("ONC-018-T03", at(2026, 9, 11, 9, 30), "neudrzim ani vodu, vsetko vyvraciam").uroven == 3
    reply = say("Mozem normalne jest a pit?", 40)
    assert reply.triage.uroven == 3 and "NAV-OPEN-EPISODE" in reply.triage.pravidla


def test_only_a_temperature_answers_the_temperature_question():
    pending = ("mám 38,5", "Píšete o teplotě 38,5 °C – je to tak?", 3)
    text, answered = navigator._followup_text(pending, "měla jsem jen 37,2")
    assert "38,5" not in text and answered
    text, answered = navigator._followup_text(pending, "zvracela jsem 2x")
    assert "38,5" in text and not answered
