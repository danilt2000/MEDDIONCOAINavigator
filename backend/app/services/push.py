"""Web Push subscriptions of real phones (kept on disk across API restarts) and sending test notifications."""

import hashlib
import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from pywebpush import WebPushException, webpush

from app.config import settings
from app.models import PRAGUE, Patient

log = logging.getLogger("api.push")

TEXTS = {
    "cs": {
        "checkin": ("MEDDI · Dotazník na dnešek", "Vyplňte prosím krátký dotazník, jak se dnes cítíte. Zabere asi 2 minuty."),
        "team": ("MEDDI · Zpráva od týmu MOÚ", "Máte novou zprávu od týmu MOÚ. Otevřete aplikaci."),
    },
    "sk": {
        "checkin": ("MEDDI · Dotazník na dnes", "Vyplňte, prosím, krátky dotazník o tom, ako sa dnes cítite. Zaberie asi 2 minúty."),
        "team": ("MEDDI · Správa od tímu MOÚ", "Máte novú správu od tímu MOÚ. Otvorte aplikáciu."),
    },
}
PATHS = {"checkin": "/checkin", "team": "/navigator"}
SERVICES = {"fcm.googleapis.com": "Google", "web.push.apple.com": "Apple", "push.services.mozilla.com": "Mozilla", "notify.windows.com": "Microsoft"}
SYSTEMS = (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Windows", "Windows"), ("Macintosh", "Mac"), ("Linux", "Linux"))
BROWSERS = (("Edg", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung Internet"), ("Firefox", "Firefox"), ("FxiOS", "Firefox"),
            ("CriOS", "Chrome"), ("Chrome", "Chrome"), ("Safari", "Safari"), ("AppleWebKit", "Safari"))
GONE = {404, 410}

_lock = threading.Lock()


def configured() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _path() -> Path:
    return settings.cache_dir / "push" / "subscriptions.json"


def _load() -> dict[str, dict]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _save(subscriptions: dict[str, dict]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(json.dumps(subscriptions, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def _now() -> str:
    return datetime.now(PRAGUE).isoformat(timespec="seconds")


def device_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:12]


def _service(endpoint: str) -> str:
    host = urlsplit(endpoint).hostname or ""
    return next((name for domain, name in SERVICES.items() if host == domain or host.endswith("." + domain)), host)


def known_service(endpoint: str) -> bool:
    return _service(endpoint) in SERVICES.values()


def _label(user_agent: str) -> str:
    system = next((name for marker, name in SYSTEMS if marker in user_agent), None)
    browser = next((name for marker, name in BROWSERS if marker in user_agent), None)
    return " · ".join(part for part in (system, browser) if part) or "Neznámé zařízení"


def _device(endpoint: str, record: dict) -> dict:
    return {
        "id": device_id(endpoint),
        "patient_id": record["patient_id"],
        "service": _service(endpoint),
        "label": _label(record["user_agent"]),
        "subscribed_at": record["subscribed_at"],
        "last_sent_at": record["last_sent_at"],
        "last_status": record["last_status"],
    }


def subscribe(patient_id: str, endpoint: str, keys: dict, user_agent: str) -> dict:
    with _lock:
        subscriptions = _load()
        record = subscriptions.get(endpoint)
        if record is None or record["patient_id"] != patient_id:
            record = {"patient_id": patient_id, "subscribed_at": _now(), "last_sent_at": None, "last_status": None}
        record.update(keys=keys, user_agent=user_agent)
        subscriptions[endpoint] = record
        _save(subscriptions)
    return _device(endpoint, record)


def unsubscribe(endpoint: str) -> bool:
    with _lock:
        subscriptions = _load()
        removed = subscriptions.pop(endpoint, None) is not None
        if removed:
            _save(subscriptions)
    return removed


def devices(patient_id: str | None = None) -> list[dict]:
    with _lock:
        subscriptions = _load()
    found = [_device(endpoint, record) for endpoint, record in subscriptions.items() if patient_id in (None, record["patient_id"])]
    return sorted(found, key=lambda device: datetime.fromisoformat(device["subscribed_at"]), reverse=True)


def templates(patient: Patient) -> list[dict]:
    query = urlencode({"patient": patient.patient_id, "from": "notification"})
    return [
        {"kind": kind, "title": title, "body": body, "url": f"{PATHS[kind]}?{query}"}
        for kind, (title, body) in TEXTS[patient.demografie.jazyk].items()
    ]


def send(patient: Patient, kind: str, target_device_id: str | None = None) -> dict | None:
    """None when the patient has no matching device. Network calls run outside the lock."""
    notification = next(template for template in templates(patient) if template["kind"] == kind)
    payload = json.dumps({"title": notification["title"], "body": notification["body"], "url": notification["url"], "tag": f"meddi-{kind}"}, ensure_ascii=False)
    with _lock:
        targets = {
            endpoint: record for endpoint, record in _load().items()
            if record["patient_id"] == patient.patient_id and target_device_id in (None, device_id(endpoint))
        }
    if not targets:
        return None
    results, outcomes = [], {}
    for endpoint, record in targets.items():
        status, error = None, None
        try:
            response = webpush(
                subscription_info={"endpoint": endpoint, "keys": record["keys"]},
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=86400,
                headers={"Urgency": "high"},
                timeout=10,
            )
            status = getattr(response, "status_code", None)
            outcomes[endpoint] = "ok"
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            error = " ".join(str(exc.message).split())[:200]
            outcomes[endpoint] = "gone" if status in GONE else (f"HTTP {status}" if status else "chyba")
        except Exception as exc:
            log.warning("push to %s failed: %r", _service(endpoint), exc)
            error = f"{type(exc).__name__}: {exc}"[:200]
            outcomes[endpoint] = type(exc).__name__
        results.append({"device_id": device_id(endpoint), "ok": error is None, "status": status, "error": error})
    sent_at = _now()
    with _lock:
        subscriptions = _load()
        for endpoint, outcome in outcomes.items():
            if endpoint not in subscriptions:
                continue
            if outcome == "gone":
                del subscriptions[endpoint]
            else:
                subscriptions[endpoint].update(last_sent_at=sent_at, last_status=outcome)
        _save(subscriptions)
    removed = sum(outcome == "gone" for outcome in outcomes.values())
    sent = sum(result["ok"] for result in results)
    return {"sent": sent, "failed": len(results) - sent - removed, "removed": removed, "notification": notification, "results": results}
