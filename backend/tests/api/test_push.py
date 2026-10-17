import hashlib
import json
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from pywebpush import WebPushException

from app.config import settings
from app.services import push

GOOGLE = "https://fcm.googleapis.com/fcm/send/device-one"
APPLE = "https://web.push.apple.com/device-two"
KEYS = {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}
ANDROID_CHROME = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36"
IPHONE_SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
WINDOWS_EDGE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0"


@pytest.fixture
def push_service(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "cache_dir", tmp_path)
    monkeypatch.setattr(settings, "vapid_public_key", "test-public-key")
    monkeypatch.setattr(settings, "vapid_private_key", "test-private-key")
    fake = SimpleNamespace(calls=[], fail={})

    def fake_webpush(**kwargs):
        endpoint = kwargs["subscription_info"]["endpoint"]
        fake.calls.append({**kwargs, "vapid_claims": dict(kwargs["vapid_claims"])})
        url = urlsplit(endpoint)
        kwargs["vapid_claims"].setdefault("aud", f"{url.scheme}://{url.netloc}")
        if endpoint in fake.fail:
            response = SimpleNamespace(status_code=fake.fail[endpoint], reason="Gone", text="")
            raise WebPushException(f"Push failed: {response.status_code} {response.reason}", response=response)
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(push, "webpush", fake_webpush)
    return fake


def subscribe(client, patient_id, endpoint, user_agent=ANDROID_CHROME):
    return client.post("/api/push/subscribe", json={"patient_id": patient_id, "subscription": {"endpoint": endpoint, "keys": KEYS}, "user_agent": user_agent})


def test_key(client, push_service, monkeypatch):
    assert client.get("/api/push/key").json() == {"public_key": "test-public-key"}
    monkeypatch.setattr(settings, "vapid_public_key", "")
    response = client.get("/api/push/key")
    assert response.status_code == 503 and response.json()["detail"]


def test_subscribe_validation(client, push_service):
    assert subscribe(client, "ONC-005", "http://fcm.googleapis.com/fcm/send/x").status_code == 422
    assert subscribe(client, "ONC-005", "https://127.0.0.1:8100/api/push/devices").status_code == 422
    assert subscribe(client, "ONC-005", "https://fcm.googleapis.com.evil.example/x").status_code == 422
    assert client.post("/api/push/subscribe", json={"patient_id": "ONC-005", "subscription": {"endpoint": GOOGLE}}).status_code == 422
    assert subscribe(client, "NOPE", GOOGLE).status_code == 404
    assert client.get("/api/push/devices").json() == []


def test_subscribe_moves_device_and_filters(client, push_service, tmp_path):
    device = subscribe(client, "ONC-005", GOOGLE).json()
    assert device["id"] == hashlib.sha256(GOOGLE.encode()).hexdigest()[:12]
    assert (device["patient_id"], device["service"], device["label"]) == ("ONC-005", "Google", "Android · Chrome")
    assert device["last_sent_at"] is None and device["last_status"] is None
    apple = subscribe(client, "ONC-001", APPLE, IPHONE_SAFARI).json()
    assert (apple["service"], apple["label"]) == ("Apple", "iPhone · Safari")
    assert push._label(WINDOWS_EDGE) == "Windows · Edge"
    assert push._service("https://updates.push.services.mozilla.com/wpush/v2/x") == "Mozilla"
    assert [item["id"] for item in client.get("/api/push/devices?patient_id=ONC-005").json()] == [device["id"]]

    assert subscribe(client, "ONC-001", GOOGLE).json()["patient_id"] == "ONC-001"
    assert client.get("/api/push/devices?patient_id=ONC-005").json() == []
    assert {item["id"] for item in client.get("/api/push/devices?patient_id=ONC-001").json()} == {device["id"], apple["id"]}
    assert len(client.get("/api/push/devices").json()) == 2
    assert set(json.loads((tmp_path / "push" / "subscriptions.json").read_text(encoding="utf-8"))) == {GOOGLE, APPLE}


def test_templates_in_patient_language(client, push_service):
    slovak = client.get("/api/push/templates?patient_id=ONC-018").json()
    assert [item["kind"] for item in slovak] == ["checkin", "team"]
    assert slovak[0] == {
        "kind": "checkin",
        "title": "MEDDI · Dotazník na dnes",
        "body": "Vyplňte, prosím, krátky dotazník o tom, ako sa dnes cítite. Zaberie asi 2 minúty.",
        "url": "/checkin?patient=ONC-018&from=notification",
    }
    assert slovak[1]["url"] == "/navigator?patient=ONC-018&from=notification"
    assert client.get("/api/push/templates?patient_id=ONC-005").json()[0]["title"] == "MEDDI · Dotazník na dnešek"
    assert client.get("/api/push/templates?patient_id=NOPE").status_code == 404


def test_send_payload(client, push_service):
    subscribe(client, "ONC-005", GOOGLE)
    apple_id = subscribe(client, "ONC-005", APPLE, IPHONE_SAFARI).json()["id"]
    result = client.post("/api/push/send", json={"patient_id": "ONC-005", "kind": "checkin"}).json()
    assert (result["sent"], result["failed"], result["removed"]) == (2, 0, 0)
    assert result["notification"]["url"] == "/checkin?patient=ONC-005&from=notification"
    assert all(item["ok"] and item["status"] == 201 and item["error"] is None for item in result["results"])
    for call in push_service.calls:
        assert json.loads(call["data"]) == {
            "title": "MEDDI · Dotazník na dnešek",
            "body": "Vyplňte prosím krátký dotazník, jak se dnes cítíte. Zabere asi 2 minuty.",
            "url": "/checkin?patient=ONC-005&from=notification",
            "tag": "meddi-checkin",
        }
        assert call["vapid_claims"] == {"sub": settings.vapid_subject}
        assert (call["vapid_private_key"], call["ttl"], call["headers"], call["timeout"]) == ("test-private-key", 86400, {"Urgency": "high"}, 10)
        assert call["subscription_info"]["keys"] == KEYS
    assert {device["last_status"] for device in client.get("/api/push/devices?patient_id=ONC-005").json()} == {"ok"}
    assert all(device["last_sent_at"] for device in client.get("/api/push/devices?patient_id=ONC-005").json())

    push_service.calls.clear()
    team = client.post("/api/push/send", json={"patient_id": "ONC-005", "kind": "team", "device_id": apple_id}).json()
    assert team["sent"] == 1 and [call["subscription_info"]["endpoint"] for call in push_service.calls] == [APPLE]
    assert json.loads(push_service.calls[0]["data"])["tag"] == "meddi-team"


def test_send_failures(client, push_service):
    subscribe(client, "ONC-005", GOOGLE)
    subscribe(client, "ONC-005", APPLE, IPHONE_SAFARI)
    push_service.fail = {GOOGLE: 410, APPLE: 403}
    result = client.post("/api/push/send", json={"patient_id": "ONC-005", "kind": "checkin"}).json()
    assert (result["sent"], result["failed"], result["removed"]) == (0, 1, 1)
    assert {item["status"] for item in result["results"]} == {410, 403} and not any(item["ok"] for item in result["results"])
    remaining = client.get("/api/push/devices?patient_id=ONC-005").json()
    assert [(device["service"], device["last_status"]) for device in remaining] == [("Apple", "HTTP 403")]


def test_unsubscribe_and_no_device(client, push_service, monkeypatch):
    subscribe(client, "ONC-005", GOOGLE)
    assert client.post("/api/push/unsubscribe", json={"endpoint": GOOGLE}).json() == {"removed": True}
    assert client.post("/api/push/unsubscribe", json={"endpoint": GOOGLE}).json() == {"removed": False}
    assert client.get("/api/push/devices").json() == []
    response = client.post("/api/push/send", json={"patient_id": "ONC-005", "kind": "checkin"})
    assert response.status_code == 404 and response.json()["detail"] == "Pacient nemá žádné zařízení se zapnutými upozorněními."
    assert client.post("/api/push/send", json={"patient_id": "NOPE", "kind": "checkin"}).status_code == 404
    assert client.post("/api/push/send", json={"patient_id": "ONC-005", "kind": "spam"}).status_code == 422
    monkeypatch.setattr(settings, "vapid_private_key", "")
    assert client.post("/api/push/send", json={"patient_id": "ONC-005", "kind": "checkin"}).status_code == 503
    assert push_service.calls == []
