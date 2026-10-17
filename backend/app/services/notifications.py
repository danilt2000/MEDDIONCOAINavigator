"""Notification rules: time rules on the demo clock (scheduler thread), event hooks, a dry-run preview and the send log.

Texts carry no health data (they show on the lock screen). Every rule fires at most once per patient per demo day;
a patient without a subscribed device is logged once as "no_device" and gets the push as soon as a device appears.
"""

import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import date, datetime
from urllib.parse import urlencode

from app import store
from app.adapters.meddi_json import load_patient, load_patients
from app.config import settings
from app.models import PRAGUE, Checkin, Patient
from app.services import push, side_effects

log = logging.getLogger("api.notifications")

TICK_SECONDS = 30
LOG_LIMIT = 500
CHANNEL = "Web Push"
CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TEAM_REPLY_ACTIONS = ("call", "telekonzultace", "close")
NOT_CONFIGURED = "Web Push není nastaven (chybí VAPID klíče)."

RULES: dict[str, dict] = {
    "daily_checkin": {
        "name": "Denní připomínka dotazníku", "kind": "time", "enabled": True, "params": {"time": "18:00"}, "opens": "/checkin",
        "description": "V nastavený čas podle demo hodin připomene dotazník pacientům, kteří dnes ještě nevyplnili check-in.",
    },
    "missed_checkin": {
        "name": "Zmeškaný dotazník", "kind": "time", "enabled": True, "params": {"days": 2}, "opens": "/checkin",
        "description": "Bez check-inu tolik dní → připomínka; dnešek se počítá až po čase denní připomínky. Pacienti s vysokým rizikem (nadir, imunoterapie) o den dřív, stejně jako v triáži.",
    },
    "team_reply": {
        "name": "Odpověď týmu", "kind": "event", "enabled": True, "params": {}, "opens": "/navigator",
        "description": "Hned, když tým ve frontě pacientovi zavolá, provede telekonzultaci nebo úkol uzavře.",
    },
    "followup": {
        "name": "Doplňující otázka", "kind": "event", "enabled": True, "params": {}, "opens": "/navigator",
        "description": "Hned, když triáž check-inu nechá pacientovi doplňující otázku.",
    },
    "quiet_hours": {
        "name": "Klidové hodiny", "kind": "quiet", "enabled": False, "params": {"start": "22:00", "end": "07:00"}, "opens": None,
        "description": "V tomto okně časová pravidla počkají do jeho konce. Odpovědi týmu a doplňující otázky chodí hned.",
    },
}

TEXTS = {
    "cs": {
        "daily_checkin": ("MEDDI · Dotazník na dnešek", "Vyplňte prosím krátký dotazník, jak se dnes cítíte. Zabere asi 2 minuty."),
        "missed_checkin": ("MEDDI · Připomínka dotazníku", "Pár dní jsme od vás nedostali dotazník. Vyplňte ho prosím, zabere asi 2 minuty."),
        "team_reply": ("MEDDI · Zpráva od týmu", "Máte novou zprávu od týmu. Otevřete aplikaci."),
        "followup": ("MEDDI · Doplňující otázka", "Máme pro vás krátkou doplňující otázku. Otevřete aplikaci."),
    },
    "sk": {
        "daily_checkin": ("MEDDI · Dotazník na dnes", "Vyplňte, prosím, krátky dotazník o tom, ako sa dnes cítite. Zaberie asi 2 minúty."),
        "missed_checkin": ("MEDDI · Pripomienka dotazníka", "Pár dní sme od vás nedostali dotazník. Vyplňte ho, prosím, zaberie asi 2 minúty."),
        "team_reply": ("MEDDI · Správa od tímu", "Máte novú správu od tímu. Otvorte aplikáciu."),
        "followup": ("MEDDI · Doplňujúca otázka", "Máme pre vás krátku doplňujúcu otázku. Otvorte aplikáciu."),
    },
}

_lock = threading.Lock()
_fired: dict[tuple[str, str, str], str] = {}
_log: list[dict] = []
_scheduler_started = False


def _path():
    return settings.cache_dir / "push" / "rules.json"


def _public(rule_id: str, enabled: bool, params: dict) -> dict:
    rule = RULES[rule_id]
    title, body = TEXTS["cs"].get(rule_id, (None, None))
    return {"id": rule_id, "name": rule["name"], "kind": rule["kind"], "description": rule["description"], "enabled": enabled,
            "params": params, "title": title, "body": body, "opens": rule["opens"]}


def load_rules() -> dict[str, dict]:
    try:
        stored = json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        stored = {}
    return {
        rule_id: _public(rule_id, stored.get(rule_id, {}).get("enabled", rule["enabled"]), {**rule["params"], **stored.get(rule_id, {}).get("params", {})})
        for rule_id, rule in RULES.items()
    }


def _check_params(rule_id: str, params: dict) -> None:
    unknown = set(params) - set(RULES[rule_id]["params"])
    if unknown:
        raise ValueError(f"Pravidlo {rule_id} nemá parametr {', '.join(sorted(unknown))}.")
    for key, value in params.items():
        if key == "days" and not (type(value) is int and 1 <= value <= 14):
            raise ValueError("Počet dní musí být celé číslo 1–14.")
        if key != "days" and not (isinstance(value, str) and CLOCK.match(value)):
            raise ValueError("Čas musí být ve formátu HH:MM.")


def save_rules(updates: list[dict]) -> dict[str, dict]:
    """updates = [{id, enabled, params}]; raises ValueError on an unknown rule or a bad parameter."""
    rules = load_rules()
    for update in updates:
        if update["id"] not in RULES:
            raise ValueError(f"Neznámé pravidlo {update['id']}.")
        _check_params(update["id"], update.get("params", {}))
        rule = rules[update["id"]]
        rules[update["id"]] = _public(rule["id"], update["enabled"], {**rule["params"], **update.get("params", {})})
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(json.dumps({rule["id"]: {"enabled": rule["enabled"], "params": rule["params"]} for rule in rules.values()}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)
    return rules


def _clock(now: datetime) -> str:
    return now.astimezone(PRAGUE).strftime("%H:%M")


def _today(now: datetime) -> date:
    return now.astimezone(PRAGUE).date()


def _day(value: date) -> str:
    return f"{value.day}. {value.month}."


def _quiet(rules: dict[str, dict], now: datetime) -> bool:
    quiet = rules["quiet_hours"]
    start, end, clock = quiet["params"]["start"], quiet["params"]["end"], _clock(now)
    return quiet["enabled"] and (start <= clock < end if start <= end else clock >= start or clock < end)


def _waiting(rule: dict, rules: dict[str, dict], now: datetime) -> str | None:
    """Why a time rule does not fire right now (None = it fires on the next tick)."""
    if _quiet(rules, now):
        return f"Klidové hodiny – odeslání počká do {rules['quiet_hours']['params']['end']}"
    if rule["id"] == "daily_checkin" and _clock(now) < rule["params"]["time"]:
        return f"Čeká na {rule['params']['time']}"
    return None


def _active(patient: Patient, today: date) -> bool:
    period = patient.obdobi_sledovani
    return period["od"] <= today and ("do" not in period or today <= period["do"])


def _last_filled(now: datetime) -> dict[str, Checkin]:
    return {checkin.patient_id: checkin for checkin in store.all_checkins() if checkin.stav == "vyplneno" and checkin.timestamp <= now}


def _daily(patients: list[Patient], now: datetime) -> list[tuple[Patient, str]]:
    today, last = _today(now), _last_filled(now)
    found = []
    for patient in patients:
        previous = last.get(patient.patient_id)
        if _active(patient, today) and not (previous and previous.datum >= today):
            found.append((patient, f"dnes bez check-inu · poslední {_day(previous.datum)}" if previous else "dnes bez check-inu · zatím žádný"))
    return found


def _missed(patients: list[Patient], now: datetime, days: int, due: str) -> list[tuple[Patient, str]]:
    """Today counts as a missed day only once today's check-in is due (the daily reminder time)."""
    from app.services.engine import build_context
    from app.triage.engine import gap_high_risk

    today, last = _today(now), _last_filled(now)
    sooner = max(1, days - 1)
    found = []
    for patient in patients:
        previous = last.get(patient.patient_id)
        since = (today - (previous.datum if previous else patient.obdobi_sledovani["od"])).days
        missed = since if _clock(now) >= due else since - 1
        if not _active(patient, today) or missed < sooner:
            continue
        high_risk = gap_high_risk(build_context(patient, now))
        if missed < (sooner if high_risk else days):
            continue
        reason = (f"poslední check-in {'včera' if since == 1 else f'před {since} dny'}" if previous
                  else f"zatím žádný check-in (sledování od {_day(patient.obdobi_sledovani['od'])})")
        found.append((patient, reason + (", vysoké riziko" if high_risk else "")))
    return found


def _team_replies(patients: list[Patient], now: datetime) -> list[tuple[Patient, str]]:
    by_id, today = {patient.patient_id: patient for patient in patients}, _today(now)
    actions = {store.ACTION_TEXT[action] for action in TEAM_REPLY_ACTIONS}
    found = {}
    for task in store.list_tasks():
        for note in task.notes:
            action = note.text.split(":")[0]
            if task.patient_id in by_id and action in actions and _today(note.at) == today and note.at <= now:
                found[task.patient_id] = (by_id[task.patient_id], f"tým: {action.lower()} v {_clock(note.at)}")
    return list(found.values())


def _followups(patients: list[Patient], now: datetime) -> list[tuple[Patient, str]]:
    from app.agent.navigator import _checkin_followup

    return [(patient, "nezodpovězená doplňující otázka z check-inu") for patient in patients if _checkin_followup(patient.patient_id, now)]


def _candidates(rule: dict, now: datetime) -> list[tuple[Patient, str]]:
    patients = list(load_patients(store.get_dataset()))
    if rule["id"] == "daily_checkin":
        return _daily(patients, now)
    if rule["id"] == "missed_checkin":
        return _missed(patients, now, rule["params"]["days"], load_rules()["daily_checkin"]["params"]["time"])
    if rule["id"] == "team_reply":
        return _team_replies(patients, now)
    if rule["id"] == "followup":
        return _followups(patients, now)
    return []


def _notification(rule_id: str, patient: Patient) -> dict:
    title, body = TEXTS[patient.demografie.jazyk][rule_id]
    query = urlencode({"patient": patient.patient_id, "from": "notification"})
    return {"kind": rule_id, "title": title, "body": body, "url": f"{RULES[rule_id]['opens']}?{query}"}


def _deliver(rule: dict, patient: Patient, reason: str, source: str, now: datetime) -> dict | None:
    """Send one rule to one patient and log it; None when the daily dedupe skips it (a manual run never skips)."""
    key = (store.generation(), rule["id"], patient.patient_id, _today(now).isoformat())
    devices = push.devices(patient.patient_id)
    with _lock:
        previous = _fired.get(key)
        if source != "manual" and (previous in ("pending", "sent", "failed") or (previous == "no_device" and not devices)):
            return None
        _fired[key] = "pending"
    result, detail = "no_device", None
    try:
        if devices and not push.configured():
            result, detail = "failed", NOT_CONFIGURED
        elif devices:
            # both check-in reminders share the manual send's tag, so the phone shows one, not two at the same tick
            kind = "checkin" if rule["opens"] == "/checkin" else rule["id"]
            outcome = push.send(patient, kind, notification=_notification(rule["id"], patient))
            errors = [item["error"] or f"HTTP {item['status']}" for item in (outcome or {}).get("results", []) if not item["ok"]]
            result = "no_device" if outcome is None else "sent" if outcome["sent"] else "failed"
            detail = "; ".join(errors)[:200] or None
    except Exception as exc:
        log.exception("notification %s to %s failed", rule["id"], patient.patient_id)
        result, detail = "failed", f"{type(exc).__name__}: {exc}"[:200]
    entry = {
        "id": uuid.uuid4().hex[:12], "at": now.isoformat(), "patient_id": patient.patient_id, "patient_name": patient.demografie.jmeno_fiktivni,
        "rule_id": rule["id"], "rule_name": rule["name"], "source": source, "reason": reason, "channel": CHANNEL,
        "device": ", ".join(device["label"] for device in devices) or None, "result": result, "detail": detail,
    }
    with _lock:
        _fired[key] = result
        _log.append(entry)
        del _log[:-LOG_LIMIT]
    return entry


def tick() -> list[dict]:
    """One scheduler pass over the time rules on the demo clock."""
    if not store.wait_ready(0):
        return []
    now = store.get_now()
    rules = load_rules()
    entries = []
    for rule in rules.values():
        if rule["kind"] == "time" and rule["enabled"] and _waiting(rule, rules, now) is None:
            entries += [entry for patient, reason in _candidates(rule, now) if (entry := _deliver(rule, patient, reason, "scheduler", now))]
    return entries


def run_now(rule_id: str) -> list[dict]:
    """The clinician's "Spustit teď": ignores the time of day, quiet hours and the daily dedupe."""
    now = store.get_now()
    rule = load_rules()[rule_id]
    return [_deliver(rule, patient, reason, "manual", now) for patient, reason in _candidates(rule, now)]


def on_event(rule_id: str, patient_id: str, reason: str) -> None:
    """Event hook (team reply, follow-up question): fires right away in the background, never fails the request."""
    def work() -> None:
        rule = load_rules()[rule_id]
        if rule["enabled"]:
            _deliver(rule, load_patient(patient_id), reason, "event", store.get_now())

    side_effects._background(f"notify-{rule_id}", work)


def _status(rule: dict, rules: dict[str, dict], now: datetime) -> tuple[str, bool]:
    if not rule["enabled"]:
        return "Vypnuto", False
    if rule["kind"] == "quiet":
        active = _quiet(rules, now)
        return (f"Teď platí, do {rule['params']['end']}" if active else "Teď neplatí"), active
    if rule["kind"] == "event":
        return "Odešle se hned při události", True
    waiting = _waiting(rule, rules, now)
    return waiting or f"Aktivní · plánovač kontroluje každých {TICK_SECONDS} s", waiting is None


def preview() -> dict:
    """Dry run: whom each rule would notify right now and why."""
    now = store.get_now()
    rules = load_rules()
    subscribed = {device["patient_id"] for device in push.devices()}
    with _lock:
        fired = dict(_fired)
    today, generation = _today(now).isoformat(), store.generation()
    items = []
    for rule in rules.values():
        status, due = _status(rule, rules, now)
        candidates = [] if rule["kind"] == "quiet" else _candidates(rule, now)
        items.append({
            "rule_id": rule["id"], "status": status, "due": due,
            "candidates": [
                {"patient_id": patient.patient_id, "patient_name": patient.demografie.jmeno_fiktivni, "reason": reason,
                 "has_device": patient.patient_id in subscribed, "fired_today": fired.get((generation, rule["id"], patient.patient_id, today))}
                for patient, reason in candidates
            ],
        })
    return {"now": now.isoformat(), "rules": items}


def get_log() -> list[dict]:
    with _lock:
        return list(reversed(_log))


def _loop() -> None:
    while True:
        time.sleep(TICK_SECONDS)
        try:
            tick()
        except Exception:
            log.exception("notification tick failed")


def start_scheduler() -> None:
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    threading.Thread(target=_loop, daemon=True, name="notifications").start()
