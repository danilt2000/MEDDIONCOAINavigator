import asyncio
from datetime import datetime

import pytest

from app import store
from app.adapters.meddi_json import load_patient
from app.agent import navigator
from app.config import settings
from app.models import PRAGUE
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
    text = navigator._followup_text(("zvracela jsem 4x a teplota 38,2", "Píšete, že jste zvracel(a) 4× za den – je to tak?", 4), "ne, jen 2x")
    assert "38,2" in text and "4x" not in text and "4×" not in text
