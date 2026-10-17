import json
from datetime import datetime

import pytest

from app import store
from app.models import PRAGUE
from app.services import engine, notifications, push, side_effects
from test_push import APPLE, GOOGLE, push_service, subscribe  # noqa: F401 (fixture)

WEDNESDAY = (2026, 9, 9)


@pytest.fixture
def rules(client, push_service, monkeypatch):
    """Fresh dedupe and log, rules in tmp, events run inline, and a settable demo clock."""
    monkeypatch.setattr(notifications, "_fired", {})
    monkeypatch.setattr(notifications, "_log", [])
    monkeypatch.setattr(side_effects, "_background", lambda name, work: work() if name.startswith("notify-") else None)

    def set_clock(hour, minute=0, day=WEDNESDAY):
        moment = datetime(*day, hour, minute, tzinfo=PRAGUE)
        monkeypatch.setattr(store, "get_now", lambda: moment)

    def put(*updates):
        return client.put("/api/notifications/rules", json=list(updates))

    return set_clock, put


def by_patient(entries):
    return {entry["patient_id"]: entry for entry in entries}


def candidates(client, rule_id):
    rule = next(item for item in client.get("/api/notifications/preview").json()["rules"] if item["rule_id"] == rule_id)
    return {item["patient_id"]: item for item in rule["candidates"]}


def test_rules_defaults_and_validation(client, rules, tmp_path):
    _, put = rules
    listed = {rule["id"]: rule for rule in client.get("/api/notifications/rules").json()}
    assert list(listed) == ["daily_checkin", "missed_checkin", "team_reply", "followup", "quiet_hours"]
    assert listed["daily_checkin"]["params"] == {"time": "18:00"} and listed["missed_checkin"]["params"] == {"days": 2}
    assert listed["quiet_hours"]["enabled"] is False and listed["quiet_hours"]["params"] == {"start": "22:00", "end": "07:00"}
    assert listed["team_reply"]["body"] == "Máte novou zprávu od týmu. Otevřete aplikaci." and listed["team_reply"]["opens"] == "/navigator"
    assert not any("MOÚ" in title + body for texts in notifications.TEXTS.values() for title, body in texts.values())

    assert put({"id": "nope", "enabled": True}).status_code == 422
    assert put({"id": "daily_checkin", "enabled": True, "params": {"time": "25:00"}}).status_code == 422
    assert put({"id": "missed_checkin", "enabled": True, "params": {"days": "2"}}).status_code == 422
    assert put({"id": "missed_checkin", "enabled": True, "params": {"hours": 2}}).status_code == 422
    saved = {rule["id"]: rule for rule in put({"id": "daily_checkin", "enabled": False, "params": {"time": "08:30"}}).json()}
    assert saved["daily_checkin"]["enabled"] is False and saved["daily_checkin"]["params"] == {"time": "08:30"}
    stored = json.loads((tmp_path / "push" / "rules.json").read_text(encoding="utf-8"))
    assert stored["daily_checkin"] == {"enabled": False, "params": {"time": "08:30"}}
    assert client.post("/api/notifications/rules/quiet_hours/run").status_code == 404


def test_daily_reminder_when_due_once_per_day(client, rules, push_service, monkeypatch):
    set_clock, put = rules
    put({"id": "missed_checkin", "enabled": False})
    subscribe(client, "ONC-009", GOOGLE)
    set_clock(17, 0)
    assert notifications.tick() == []
    assert "ONC-009" in candidates(client, "daily_checkin")

    set_clock(18, 5)
    entries = by_patient(notifications.tick())
    assert entries["ONC-009"]["result"] == "sent" and entries["ONC-009"]["device"] == "Android · Chrome"
    assert entries["ONC-009"]["reason"] == "dnes bez check-inu · poslední 6. 9." and entries["ONC-009"]["at"].startswith("2026-09-09T18:05")
    assert entries["ONC-016"]["result"] == "no_device"
    assert "ONC-004" not in entries and "ONC-013" not in entries
    assert json.loads(push_service.calls[0]["data"]) == {
        "title": "MEDDI · Dotazník na dnešek",
        "body": "Vyplňte prosím krátký dotazník, jak se dnes cítíte. Zabere asi 2 minuty.",
        "url": "/checkin?patient=ONC-009&from=notification",
        "tag": "meddi-checkin",
    }

    set_clock(18, 35)
    assert notifications.tick() == []
    assert len(push_service.calls) == 1
    assert candidates(client, "daily_checkin")["ONC-009"]["fired_today"] == "sent"
    assert len(client.get("/api/notifications/log").json()) == len(entries)

    subscribe(client, "ONC-016", APPLE)
    assert by_patient(notifications.tick())["ONC-016"]["result"] == "sent"

    generation = store.generation()
    monkeypatch.setattr(store, "generation", lambda: generation + 1)
    assert by_patient(notifications.tick())["ONC-009"]["result"] == "sent"


def test_missed_checkin_one_day_sooner_for_high_risk(client, rules):
    set_clock, put = rules
    set_clock(18, 30)
    missed = candidates(client, "missed_checkin")
    assert missed["ONC-009"]["reason"] == "poslední check-in před 3 dny"
    assert missed["ONC-001"]["reason"] == "poslední check-in včera, vysoké riziko"
    assert "ONC-005" not in missed

    set_clock(12, 0)
    missed = candidates(client, "missed_checkin")
    assert missed["ONC-004"]["reason"] == "poslední check-in před 2 dny, vysoké riziko"
    assert "ONC-001" not in missed and "ONC-002" not in missed
    set_clock(0, 1, (2026, 9, 10))
    assert "ONC-010" not in candidates(client, "missed_checkin")

    put({"id": "missed_checkin", "enabled": True, "params": {"days": 3}})
    set_clock(18, 30, (2026, 9, 10))
    missed = candidates(client, "missed_checkin")
    assert {"ONC-009", "ONC-002"} <= set(missed) and "ONC-010" not in missed
    assert missed["ONC-001"]["reason"] == "poslední check-in před 2 dny, vysoké riziko"


def test_quiet_hours_hold_time_rules_but_not_a_manual_run(client, rules, push_service):
    set_clock, put = rules
    subscribe(client, "ONC-009", GOOGLE)
    put({"id": "quiet_hours", "enabled": True, "params": {"start": "21:00", "end": "07:00"}})
    set_clock(21, 30)
    assert notifications.tick() == []
    daily = next(item for item in client.get("/api/notifications/preview").json()["rules"] if item["rule_id"] == "daily_checkin")
    assert daily["status"] == "Klidové hodiny – odeslání počká do 07:00" and daily["due"] is False

    manual = by_patient(client.post("/api/notifications/rules/daily_checkin/run").json())
    assert manual["ONC-009"]["result"] == "sent" and manual["ONC-009"]["source"] == "manual"

    put({"id": "quiet_hours", "enabled": True, "params": {"start": "21:00", "end": "21:15"}})
    assert {entry["rule_id"] for entry in notifications.tick()} == {"missed_checkin"}
    assert {json.loads(call["data"])["tag"] for call in push_service.calls} == {"meddi-checkin"}


def test_team_reply_hook(client, rules, push_service):
    set_clock, _ = rules
    set_clock(21, 40)
    task = store.list_tasks()[0]
    subscribe(client, task.patient_id, GOOGLE)
    client.post(f"/api/tasks/{task.id}/action", json={"action": "accept"})
    assert notifications.get_log() == []

    client.post(f"/api/tasks/{task.id}/action", json={"action": "call", "note": "domluveno"})
    [entry] = notifications.get_log()
    assert (entry["rule_id"], entry["source"], entry["result"], entry["reason"]) == ("team_reply", "event", "sent", "tým: telefonát s pacientem")
    payload = json.loads(push_service.calls[0]["data"])
    assert payload["body"] == "Máte novou zprávu od týmu. Otevřete aplikaci."
    assert payload["url"] == f"/navigator?patient={task.patient_id}&from=notification"
    assert candidates(client, "team_reply")[task.patient_id]["reason"] == "tým: telefonát s pacientem v 21:40"

    client.post(f"/api/tasks/{task.id}/action", json={"action": "close"})
    assert len(notifications.get_log()) == 1


def test_push_failure_never_crashes(client, rules, monkeypatch):
    set_clock, _ = rules
    subscribe(client, "ONC-009", GOOGLE)
    set_clock(18, 5)

    def broken(*args, **kwargs):
        raise RuntimeError("push service down")

    monkeypatch.setattr(push, "send", broken)
    entry = by_patient(notifications.tick())["ONC-009"]
    assert (entry["result"], entry["detail"]) == ("failed", "RuntimeError: push service down")
    assert notifications.tick() == []
    notifications.on_event("team_reply", "ONC-009", "tým: uzavřeno")
    assert notifications.get_log()[0]["result"] == "failed"


def test_followup_hook(client, rules, push_service, monkeypatch):
    set_clock, _ = rules
    set_clock(8, 0, (2026, 9, 10))
    subscribe(client, "ONC-016", GOOGLE)
    real = engine.run_checkin

    def with_question(*args):
        ctx, nlu, output = real(*args)
        return ctx, nlu, output.model_copy(update={"doplnujici_otazka": "Kolikrát za den?"})

    monkeypatch.setattr(engine, "run_checkin", with_question)
    assert client.post("/api/checkins", json={"patient_id": "ONC-016", "zprava_pacienta": "Dnes dobrý."}).status_code == 200
    [entry] = notifications.get_log()
    assert (entry["rule_id"], entry["patient_id"], entry["result"]) == ("followup", "ONC-016", "sent")
    payload = json.loads(push_service.calls[0]["data"])
    assert payload["url"] == "/navigator?patient=ONC-016&from=notification" and "Kolikrát" not in payload["body"]
