"""Response shapes must match packages/api/src/types.ts."""

import json
from datetime import datetime

from app.models import PRAGUE, TriageOutput

TRIAGE_KEYS = set(TriageOutput.model_fields)
QUEUE_TASK_KEYS = {"id", "patient_id", "checkin_id", "uroven", "priority", "status", "owner", "why", "out_of_hours", "created", "sla_do", "notes"}
QUEUE_ITEM_KEYS = QUEUE_TASK_KEYS | {"patient_name", "age", "regimen", "cycle_day"}
LIST_ITEM_KEYS = {
    "patient_id", "dataset", "name", "age", "sex", "lang", "diagnosis", "regimen", "cycle", "cycle_day",
    "risk_badges", "filled_by", "last_level", "last_checkin_at", "open_task",
}
DETAIL_KEYS = LIST_ITEM_KEYS | {"stage", "icd10", "intent", "ecog", "comorbidities", "allergies", "advance_directive", "meds", "monitoring"}
CONTEXT_KEYS = {
    "patient_id", "as_of", "age", "sex", "lang", "filled_by_default", "diagnosis", "regimen", "intent", "cycle", "cycle_day",
    "in_nadir", "chemo_window", "drug_classes", "meds", "comorbidities", "allergies", "advance_directive", "baselines",
}
SUMMARY_KEYS = {"patient_id", "as_of", "reason", "header", "proc_ted", "lecba", "vyvoj", "laborator", "nehlasi", "k_posouzeni", "facts", "text", "generated_by"}
FEVER_CHECKIN = {
    "patient_id": "ONC-001",
    "stav": "vyplneno",
    "vyplnil": "pacient",
    "dotazniky": [
        {
            "dotaznik_id": "nezadouci_ucinky",
            "odpovedi": [
                {"otazka_id": "pocit", "odpoved_index": 3},
                {"otazka_id": "ucinky", "odpoved_index": [5, 7]},
                {"otazka_id": "teplota", "odpoved_index": 1},
            ],
        }
    ],
    "vitalni_funkce": {"teplota_c": 38.4},
    "zprava_pacienta": "mam 38,4 a trese me zima",
}


def test_meta(client):
    assert set(client.get("/api/health").json()) == {"iris", "fhir", "llm", "mcp", "version"}
    state = client.get("/api/demo/state").json()
    assert set(state) == {"now", "dataset"} and state["dataset"] == "dev"
    assert datetime.fromisoformat(state["now"]) >= datetime(2026, 9, 9, 21, 50, tzinfo=PRAGUE)
    assert [item["id"] for item in client.get("/api/questionnaires").json()] == ["nezadouci_ucinky", "psychoonkologicky_screening", "bolest_analgeticka_terapie", "esas"]
    contacts = client.get("/api/contacts").json()
    assert set(contacts) == {"monitoring_centre", "on_duty", "ems"} and contacts["on_duty"]["phone"] == "724 590 848"


def test_patients(client):
    patients = client.get("/api/patients").json()
    assert len(patients) == 14 and all(set(item) == LIST_ITEM_KEYS for item in patients)
    jana = next(item for item in patients if item["patient_id"] == "ONC-001")
    assert jana["cycle_day"] == 10 and "nadir" in jana["risk_badges"] and jana["last_level"] is not None
    assert len(client.get("/api/patients?dataset=rozsirena").json()) == 100
    assert set(client.get("/api/patients/ONC-004").json()) == DETAIL_KEYS
    assert client.get("/api/patients/NOPE").status_code == 404


def test_patient_views(client):
    assert CONTEXT_KEYS <= set(client.get("/api/patients/ONC-001/context").json())
    timeline = client.get("/api/patients/ONC-001/timeline").json()
    assert {item["kind"] for item in timeline} >= {"checkin", "lab"}
    assert all({"kind", "at", "title", "detail", "ref"} <= set(item) for item in timeline)
    assert [item["at"] for item in timeline] == sorted(item["at"] for item in timeline)
    assert all(item["at"] <= "2026-09-09T21:51" for item in timeline)
    for metric in ("weight", "bp_sys", "bp_dia", "pulse", "temperature", "glucose", "stools", "pain"):
        trend = client.get(f"/api/patients/ONC-014/trends?metric={metric}&days=60").json()
        assert set(trend) == {"metric", "unit", "points"} and trend["metric"] == metric
    assert client.get("/api/patients/ONC-014/trends?metric=pain&days=60").json()["points"]
    triage = client.get("/api/patients/ONC-004/triage").json()
    assert triage and set(triage[0]) == TRIAGE_KEYS and triage[0]["as_of"] >= triage[-1]["as_of"]
    assert set(client.get("/api/patients/ONC-004/summary").json()) == SUMMARY_KEYS


def test_checkin_task_lifecycle(client):
    output = client.post("/api/checkins", json=FEVER_CHECKIN).json()
    assert set(output) == TRIAGE_KEYS
    assert output["checkin_id"].startswith("ONC-001-P") and output["uroven"] >= 2
    assert client.get(f"/api/checkins/{output['checkin_id']}/triage").json()["uroven"] == output["uroven"]
    assert client.post("/api/checkins", json={**FEVER_CHECKIN, "checkin_id": output["checkin_id"]}).json() == output
    queue = client.get("/api/queue").json()
    assert all(set(item) == QUEUE_ITEM_KEYS for item in queue)
    assert [-item["uroven"] for item in queue] == sorted(-item["uroven"] for item in queue)
    task = next(item for item in queue if item["patient_id"] == "ONC-001")
    assert task["checkin_id"] == output["checkin_id"] and task["cycle_day"] == 10
    accepted = client.post(f"/api/tasks/{task['id']}/action", json={"action": "accept", "note": "volám"}).json()
    assert accepted["status"] == "accepted" and accepted["notes"][-1]["text"] == "Převzato: volám"
    assert client.get("/api/stats/kpi").json()["median_minutes_to_accept"] is not None
    assert client.post(f"/api/tasks/{task['id']}/action", json={"action": "call", "note": "doporučen příjem"}).json()["status"] == "in-progress"
    assert client.post(f"/api/tasks/{task['id']}/action", json={"action": "accept"}).json()["status"] == "in-progress"
    team_events = [item for item in client.get("/api/patients/ONC-001/timeline").json() if item["kind"] == "team_event"]
    assert team_events and "doporučen příjem" in team_events[-1]["detail"]
    assert client.post(f"/api/tasks/{task['id']}/action", json={"action": "close"}).json()["status"] == "completed"
    assert all(item["id"] != task["id"] for item in client.get("/api/queue").json())
    assert client.post("/api/tasks/T-NOPE/action", json={"action": "close"}).status_code == 404
    timeline = client.get(f"/api/patients/ONC-001/timeline?as_of={output['as_of'].replace('+', '%2B')}").json()
    assert output["checkin_id"] in [item["ref"] for item in timeline]


def test_new_escalation_raises_open_task(client):
    from app import store

    base = client.get("/api/patients/ONC-005/triage").json()[0]
    first = store.raise_task(TriageOutput.model_validate({**base, "checkin_id": "X-1", "uroven": 2, "sla_do": None}), side_effects=False)
    second = store.raise_task(TriageOutput.model_validate({**base, "checkin_id": "X-2", "uroven": 4, "sla_do": None}), side_effects=False)
    lower = store.raise_task(TriageOutput.model_validate({**base, "checkin_id": "X-3", "uroven": 2, "sla_do": None}), side_effects=False)
    assert first.id == second.id == lower.id
    assert lower.uroven == 4 and lower.priority == "stat" and lower.checkin_id == "X-3" and len(lower.notes) >= 2
    store.apply_task_action(first.id, "close", None, "test")


def test_stats(client):
    kpi = client.get("/api/stats/kpi").json()
    assert set(kpi) == {"today_by_level", "open_tasks", "sla_breached", "missed_checkins", "median_minutes_to_accept"}
    assert set(kpi["today_by_level"]) == {"1", "2", "3", "4"}
    daily = client.get("/api/stats/daily?from=2026-09-01&to=2026-09-09").json()
    assert len(daily) == 9 and set(daily[0]) == {"date", "by_level", "checkins", "missed"}
    symptoms = client.get("/api/stats/symptoms").json()
    assert symptoms and set(symptoms[0]) == {"symptom", "patients", "alerts", "reports"}
    day = client.get("/api/stats/day/2026-09-09").json()
    assert all(set(row) == QUEUE_ITEM_KEYS for row in day)
    rows = client.get(f"/api/stats/symptom/{symptoms[0]['symptom']}").json()
    assert rows and set(rows[0]) == {"patient_id", "name", "regimen", "risk_badges", "max_grade", "series"}
    assert client.get("/api/stats/symptom/Nic").status_code == 404
    mine = client.get(f"/api/stats/patient/{rows[0]['patient_id']}/symptoms").json()
    assert symptoms[0]["symptom"] in {row["symptom"] for row in mine}
    assert set(mine[0]) == {"symptom", "max_grade", "reports"}


def test_clear_chat(client):
    assert client.delete("/api/chat/ONC-005/messages").json() == []
    assert client.get("/api/chat/ONC-005/messages").json() == []
    assert client.delete("/api/chat/NOPE/messages").status_code == 404


def test_replay_and_eval(client):
    run_id = client.post("/api/replay", json={"dataset": "dev", "patients": ["ONC-004"], "speed": 0}).json()["run_id"]
    events = []
    with client.stream("GET", f"/api/replay/{run_id}/events") as response:
        event = None
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                events.append((event, json.loads(line[5:])))
    names = [name for name, _ in events]
    assert names[-1] == "end" and names.count("checkin") >= 6
    first = events[0][1]
    assert set(first) == {"checkin_id", "patient_id", "at", "output", "expected"} and first["expected"]["checkin_id"] == first["checkin_id"]
    report = client.get(f"/api/eval/{run_id}").json()
    assert {"metrics", "confusion", "errors"} <= set(report) and len(report["confusion"]) == 4
    assert client.get("/api/eval/latest-dev").status_code in (200, 404)
    assert client.get("/api/eval/nope").status_code == 404


def test_demo_state_reset(client):
    state = client.post("/api/demo/state", json={"now": "2026-09-01T08:00:00+02:00"}).json()
    assert state["now"].startswith("2026-09-01T08:00") and state["dataset"] == "dev"
    patients = client.get("/api/patients").json()
    assert all(item["last_checkin_at"] is None or item["last_checkin_at"] < "2026-09-01T08:01" for item in patients)
    assert all(item["created"] < "2026-09-01T08:01" for item in client.get("/api/queue?status=all").json())
    assert client.post("/api/demo/state", json={"dataset": "nope"}).status_code == 422
    restored = client.post("/api/demo/state", json={"now": "2026-09-09T21:50:00+02:00", "dataset": "dev"}).json()
    assert restored["now"].startswith("2026-09-09T21:50")
