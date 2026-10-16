"""Live check-in: fill missing fields from the demo clock, triage, store, alert."""

import logging
import threading

from app import store
from app.adapters.meddi_json import load_questionnaires
from app.models import PRAGUE, Checkin, Patient, TriageOutput
from app.services import engine, side_effects

log = logging.getLogger("api.pipeline")

COLOUR_RANK = {"zelena": 1, "zluta": 2, "cervena": 3}
CHECKIN_FIELDS = set(Checkin.model_fields)


def _definitions() -> dict[str, dict]:
    return {questionnaire["id"]: questionnaire for questionnaire in load_questionnaires()}


def _fill_answer(answer: dict, question: dict | None) -> dict:
    filled = {"odpoved": None, "odpoved_index": None, "barva": None, "upozorneni": None, **answer}
    options = (question or {}).get("moznosti") or []
    index = filled["odpoved_index"]
    filled.setdefault("otazka", (question or {}).get("text", filled["otazka_id"]))
    if isinstance(index, int) and 0 <= index < len(options):
        option = options[index]
        filled["odpoved"] = filled["odpoved"] if filled["odpoved"] is not None else option["text"]
        filled["barva"] = filled["barva"] or option.get("barva")
        filled["upozorneni"] = filled["upozorneni"] or option.get("upozorneni")
    elif isinstance(index, list) and filled["odpoved"] is None:
        filled["odpoved"] = [options[item]["text"] for item in index if 0 <= item < len(options)]
    return filled


def _fill_questionnaire(fill: dict, checkin_id: str, definitions: dict[str, dict]) -> dict:
    definition = definitions.get(fill.get("dotaznik_id", ""), {})
    questions = {question["id"]: question for question in definition.get("otazky", [])}
    answers = [_fill_answer(answer, questions.get(answer.get("otazka_id"))) for answer in fill.get("odpovedi", [])]
    colours = [answer["barva"] for answer in answers if answer["barva"] in COLOUR_RANK]
    return {
        "vyplneni_id": fill.get("vyplneni_id") or f"{checkin_id}-{fill.get('dotaznik_id', 'Q')}",
        "dotaznik_id": fill.get("dotaznik_id"),
        "dotaznik_nazev": fill.get("dotaznik_nazev") or definition.get("nazev", ""),
        "odpovedi": answers,
        "nejvyssi_barva": fill.get("nejvyssi_barva") or (max(colours, key=COLOUR_RANK.get) if colours else None),
        "zobrazena_upozorneni": fill.get("zobrazena_upozorneni") or [answer["upozorneni"] for answer in answers if answer["upozorneni"]],
    }


def _new_checkin_id(patient: Patient) -> str:
    taken = {checkin.checkin_id for checkin in patient.checkiny} | {checkin.checkin_id for checkin in store.all_checkins()}
    number = len(store.live_checkins(patient.patient_id)) + 1
    while f"{patient.patient_id}-L{number:02d}" in taken:
        number += 1
    return f"{patient.patient_id}-L{number:02d}"


def normalize_checkin(body: dict, patient: Patient) -> Checkin:
    now = store.get_now().astimezone(PRAGUE)
    data = {key: value for key, value in body.items() if key in CHECKIN_FIELDS}
    data["patient_id"] = patient.patient_id
    data["checkin_id"] = data.get("checkin_id") or _new_checkin_id(patient)
    data["datum"] = data.get("datum") or now.date().isoformat()
    data["cas"] = data.get("cas") or now.strftime("%H:%M")
    data["stav"] = data.get("stav") or "vyplneno"
    data["vyplnil"] = data.get("vyplnil") or "pacient"
    data["prilohy"] = data.get("prilohy") or []
    vitals = data.get("vitalni_funkce") or None
    if vitals:
        data["vitalni_funkce"] = {
            name: value if isinstance(value, dict) else {"hodnota": value, "zdroj": "pacient"}
            for name, value in vitals.items()
            if value is not None
        }
    definitions = _definitions()
    data["dotazniky"] = [_fill_questionnaire(fill, data["checkin_id"], definitions) for fill in data.get("dotazniky") or []]
    checkin = Checkin.model_validate({**data, "den_sledovani": data.get("den_sledovani") or 0})
    if not body.get("den_sledovani"):
        checkin.den_sledovani = (checkin.datum - patient.obdobi_sledovani["od"]).days + 1
    if checkin.cyklus is None and checkin.den_cyklu is None:
        checkin.cyklus, checkin.den_cyklu = engine._cycle_at(patient, checkin.datum)
    return checkin


def process_checkin(patient: Patient, checkin: Checkin) -> TriageOutput:
    already = store.get_output(checkin.checkin_id)
    if already is not None:
        return already
    is_live = checkin.checkin_id not in {item.checkin_id for item in patient.checkiny}
    patient = store.with_live_events(patient)
    previous = store.live_checkins(patient.patient_id)
    ctx, nlu, output = engine.run_checkin(patient, checkin, previous, engine.use_llm_default())
    store.record_output(checkin, output, live=is_live, nlu=nlu)
    if output.uroven >= 2:
        store.raise_task(output)
    threading.Thread(target=_after_checkin, args=(patient, checkin, output), daemon=True, name="after-checkin").start()
    return output


def _after_checkin(patient: Patient, checkin: Checkin, output: TriageOutput) -> None:
    summary = None
    if output.uroven >= 3:
        try:
            ctx = engine.build_context(patient, checkin.timestamp, store.live_checkins(patient.patient_id))
            summary = engine.build_summary(patient, ctx, store.get_patient_outputs(patient.patient_id), "eskalace")
            store.set_summary(summary)
        except Exception:
            log.exception("summary for %s failed", checkin.checkin_id)
    side_effects.dispatch_checkin(patient, checkin, output, summary)
