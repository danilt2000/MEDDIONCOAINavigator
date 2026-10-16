from datetime import timedelta

from app import store


def test_raised_task_needs_a_new_takeover_and_gets_a_fresh_escalation_time(client):
    task = next(task for task in store.list_tasks() if task.patient_id == "ONC-004" and task.status != "completed")
    client.post(f"/api/tasks/{task.id}/action", json={"action": "accept"})
    escalation = store.get_output(task.checkin_id).model_copy(update={
        "checkin_id": "ONC-004-TEST", "uroven": 4, "as_of": store.get_now(), "sla_do": store.get_now() + timedelta(minutes=15),
        "varovne_priznaky": ["krev ve stolici"], "zdroj": "checkin"})
    raised = store.raise_task(escalation, side_effects=False)
    assert raised.id == task.id and raised.uroven == 4
    assert raised.status == "requested"
    assert raised.created == escalation.as_of


def test_accepted_in_time_is_not_a_breach(client):
    task = next(task for task in store.list_tasks() if task.status == "requested" and task.sla_do and task.sla_do > store.get_now())
    assert store.sla_breached(task, task.sla_do + timedelta(hours=1))
    client.post(f"/api/tasks/{task.id}/action", json={"action": "accept"})
    assert not store.sla_breached(store.get_task(task.id), task.sla_do + timedelta(hours=1))


def test_timeline_shows_only_processed_checkins(client, monkeypatch):
    later = store.replay_cutoff() + timedelta(hours=1)
    monkeypatch.setattr(store, "get_now", lambda: later)
    items = client.get("/api/patients/ONC-001/timeline").json()
    assert all(item["level"] is not None for item in items if item["kind"] == "checkin")
    assert not any(item["ref"] == "ONC-001-C07" for item in items)
