"""MEDDI JSON and navigator outputs -> FHIR R4 resources (plain dicts), spec §7.

Every resource gets a deterministic id, so a PUT transaction is idempotent and needs no lookups.
"""

import base64
import hashlib
import html
import re
import unicodedata
from datetime import date, datetime

from app.config import settings
from app.models import Checkin, DoctorSummary, Lab, Lek, Patient, QueueTask, TeamEvent, TriageOutput

EXT = "urn:meddi:fhir:ext:"
LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
DEVICE_ID = "meddi-navigator"
DEVICE_REF = f"Device/{DEVICE_ID}"
QUESTIONNAIRE_URL = "urn:meddi:questionnaire:"
LEVEL_NAMES = {1: "Zelená", 2: "Žlutá", 3: "Oranžová", 4: "Červená"}

LAB_LOINC = {
    "leu": "6690-2", "neu": "751-8", "hb": "718-7", "plt": "777-3", "kreat": "14682-9", "na": "2951-2",
    "k": "2823-3", "alt": "1742-6", "bili": "14631-6", "crp": "1988-5", "tsh": "3016-3", "ft4": "14920-3",
    "mg": "2601-3", "inr": "6301-6", "alb": "1751-7", "psa": "2857-1", "testo": "14913-8", "glu": "14749-6",
    "moc_bilk": "20454-5", "ntprobnp": "33762-6",
}

# key -> (LOINC, display, UCUM code, unit)
VITALS = {
    "teplota_c": ("8310-5", "Body temperature", "Cel", "°C"),
    "tepova_frekvence": ("8867-4", "Heart rate", "/min", "/min"),
    "dechova_frekvence": ("9279-1", "Respiratory rate", "/min", "/min"),
    "spo2": ("59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry", "%", "%"),
    "vaha_kg": ("29463-7", "Body weight", "kg", "kg"),
    "glykemie_mmol_l": ("14743-9", "Glucose [Moles/volume] in Capillary blood by Glucometer", "mmol/L", "mmol/l"),
}

# §8.4: class -> name stems, matched on lower-case text without diacritics
DRUG_CLASSES = {
    "cytotoxic": ["doxorubicin", "cyklofosfamid", "cyclophosphamid", "oxaliplatin", "5-fu", "fluorouracil",
                  "irinotekan", "irinotecan", "karboplatin", "carboplatin", "etoposid", "cisplatin",
                  "kapecitabin", "capecitabin", "vinkristin", "vincristin", "paklitaxel", "paclitaxel"],
    "immunotherapy": ["ipilimumab", "nivolumab", "atezolizumab", "pembrolizumab"],
    "fluoropyrimidine": ["5-fu", "fluorouracil", "kapecitabin", "capecitabin"],
    "irinotecan": ["irinotekan", "irinotecan"],
    "anticoagulant": ["warfarin"],
    "antiangiogenic": ["sunitinib", "bevacizumab"],
    "cardiotoxic": ["doxorubicin", "epirubicin", "trastuzumab"],
    "platinum": ["cisplatin", "karboplatin", "carboplatin"],
    "neurotoxic": ["oxaliplatin", "vinkristin", "vincristin", "paklitaxel", "paclitaxel"],
    "corticosteroid": ["dexametazon", "dexamethason", "prednison"],
    "opioid": ["morfin", "morphin", "oramorph"],
    "insulin": ["inzulin", "insulin"],
    "metformin": ["metformin"],
}
REGIMENS = {
    "r-chop": "rituximab cyklofosfamid doxorubicin vinkristin prednison",
    "folfox": "5-fu leukovorin oxaliplatin",
    "folfiri": "5-fu leukovorin irinotekan",
    "ac (": "doxorubicin cyklofosfamid",
}

RELATIONSHIPS = {"dcera": "DAU", "syn": "SON", "manzelka": "WIFE", "manzel": "HUSB", "vnucka": "GRNDDAU"}

SECTION_TITLES = [
    ("proc_ted", "Proč teď / K rozhodnutí"), ("lecba", "Léčba"), ("vyvoj", "Vývoj"),
    ("laborator", "Laboratoř"), ("nehlasi", "Nehlásí"), ("k_posouzeni", "K posouzení"),
]
GRADE_FINDING = re.compile(r"(?P<name>[^,;:()]+?)\s+G(?P<grade>[1-5])\b(?:\s*\((?P<source>[^)]*)\))?")


def ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def fhir_id(*parts) -> str:
    raw = "-".join(str(part) for part in parts)
    clean = re.sub(r"[^A-Za-z0-9.-]+", "-", ascii_fold(raw)).strip("-")
    return clean if len(clean) <= 64 else f"{clean[:55]}-{hashlib.sha1(raw.encode()).hexdigest()[:8]}"


def drug_classes(text: str) -> list[str]:
    folded = ascii_fold(text).lower()
    for acronym, drugs in REGIMENS.items():
        if acronym in folded:
            folded += " " + drugs
    return [name for name, stems in DRUG_CLASSES.items() if any(stem in folded for stem in stems)]


def meta(dataset: str, *extra_tags: dict) -> dict:
    return {"tag": [
        {"system": "urn:meddi:tag", "code": "synthetic"},
        {"system": "urn:meddi:dataset", "code": dataset},
        *extra_tags,
    ]}


def class_tags(classes: list[str]) -> list[dict]:
    return [{"system": "urn:meddi:drug-class", "code": name} for name in classes]


def ref(resource_type: str, resource_id: str, display: str | None = None) -> dict:
    reference = {"reference": f"{resource_type}/{resource_id}"}
    if display:
        reference["display"] = display
    return reference


def reference_of(resource: dict) -> str:
    return f"{resource['resourceType']}/{resource['id']}"


def ext(name: str, **value) -> dict:
    return {"url": EXT + name, **value}


def concept(system: str, code: str, display: str | None = None, text: str | None = None) -> dict:
    coding = {"system": system, "code": code}
    if display:
        coding["display"] = display
    result = {"coding": [coding]}
    if text or display:
        result["text"] = text or display
    return result


def iso(value: date | datetime) -> str:
    return value.isoformat()


def narrative(text: str) -> dict:
    body = html.escape(text).replace("\n", "<br/>")
    return {"status": "generated", "div": f'<div xmlns="http://www.w3.org/1999/xhtml">{body}</div>'}


def checkin_identifier(checkin_id: str) -> dict:
    return {"system": "urn:meddi:checkin", "value": checkin_id}


# ---------- people ----------

def relation_of(filled_by: str) -> str | None:
    """'dcera' -> 'dcera'; 'pacient (pomáhá manželka)' -> 'manželka'; 'pacient' -> None."""
    match = re.search(r"\((?:pomáhá\s+)?([^)]+)\)", filled_by)
    if match:
        return match.group(1).strip()
    return None if filled_by.startswith("pacient") else filled_by.strip()


def related_person_id(patient_id: str, relation: str) -> str:
    return fhir_id(patient_id, ascii_fold(relation).lower())


def author_ref(patient_id: str, filled_by: str) -> dict:
    relation = relation_of(filled_by)
    if relation is None:
        return ref("Patient", patient_id)
    return ref("RelatedPerson", related_person_id(patient_id, relation), relation)


def related_person(patient_id: str, relation: str, dataset: str) -> dict:
    code = RELATIONSHIPS.get(ascii_fold(relation).lower(), "FAMMEMB")
    return {
        "resourceType": "RelatedPerson",
        "id": related_person_id(patient_id, relation),
        "meta": meta(dataset),
        "identifier": [{"system": "urn:meddi:related-person", "value": related_person_id(patient_id, relation)}],
        "active": True,
        "patient": ref("Patient", patient_id),
        "relationship": [concept("http://terminology.hl7.org/CodeSystem/v3-RoleCode", code, text=relation)],
        "name": [{"text": f"{relation} (pečující)"}],
    }


def navigator_device(version: str = "engine 0.1.0") -> dict:
    return {
        "resourceType": "Device",
        "id": DEVICE_ID,
        "meta": meta("dev"),
        "identifier": [{"system": "urn:meddi:device", "value": DEVICE_ID}],
        "status": "active",
        "deviceName": [{"name": "MEDDI navigátor", "type": "user-friendly-name"}],
        "type": {"text": "AI navigátor pacienta mezi kontrolami (software)"},
        "version": [{"value": version}, {"type": {"text": "LLM"}, "value": settings.llm_model}],
    }


# ---------- patient record (seed) ----------

def patient_resource(patient: Patient) -> dict:
    demo = patient.demografie
    name_parts = demo.jmeno_fiktivni.split()
    start = patient.obdobi_sledovani["od"]
    return {
        "resourceType": "Patient",
        "id": fhir_id(patient.patient_id),
        "meta": meta(patient.sada),
        "identifier": [{"system": "urn:meddi:patient", "value": patient.patient_id}],
        "active": True,
        "name": [{"text": demo.jmeno_fiktivni, "family": name_parts[-1], "given": name_parts[:-1]}],
        "gender": {"F": "female", "M": "male"}.get(demo.pohlavi, "unknown"),
        "_birthDate": {"extension": [ext("birthdate-approximate", valueBoolean=True)]},
        "birthDate": str(start.year - demo.vek),
        "address": [{"state": demo.kraj, "country": "CZ"}],
        "communication": [{"language": concept("urn:ietf:bcp:47", demo.jazyk, text=demo.jazyk), "preferred": True}],
        "extension": [
            ext("age-at-start", valueInteger=demo.vek),
            ext("household", valueString=demo.domacnost),
            ext("digital-literacy", valueString=demo.digitalni_gramotnost),
            ext("filled-by", valueString=demo.vyplnuje),
        ],
    }


def condition_resources(patient: Patient) -> list[dict]:
    pid, dataset, dx = patient.patient_id, patient.sada, patient.diagnoza
    active = concept("http://terminology.hl7.org/CodeSystem/condition-clinical", "active")
    primary = {
        "resourceType": "Condition",
        "id": fhir_id(pid, "dx"),
        "meta": meta(dataset),
        "identifier": [{"system": "urn:meddi:condition", "value": fhir_id(pid, "dx")}],
        "clinicalStatus": active,
        "verificationStatus": concept("http://terminology.hl7.org/CodeSystem/condition-ver-status", "confirmed"),
        "category": [concept("http://terminology.hl7.org/CodeSystem/condition-category", "encounter-diagnosis")],
        "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": dx.mkn10, "display": dx.diagnoza}],
                 "text": dx.diagnoza},
        "subject": ref("Patient", pid),
        "onsetDateTime": dx.datum_diagnozy,
        "stage": [{"summary": {"text": dx.stadium}}],
        "note": [{"text": f"Biomarkery: {dx.biomarkery}"}],
    }
    comorbidities = [{
        "resourceType": "Condition",
        "id": fhir_id(pid, "cm", index),
        "meta": meta(dataset),
        "clinicalStatus": active,
        "category": [concept("http://terminology.hl7.org/CodeSystem/condition-category", "problem-list-item")],
        "code": {"text": text},
        "subject": ref("Patient", pid),
    } for index, text in enumerate(patient.komorbidity, 1)]
    return [primary, *comorbidities]


def allergy_resources(patient: Patient) -> list[dict]:
    return [{
        "resourceType": "AllergyIntolerance",
        "id": fhir_id(patient.patient_id, "allergy", index),
        "meta": meta(patient.sada),
        "clinicalStatus": concept("http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "active"),
        "code": {"text": text},
        "patient": ref("Patient", patient.patient_id),
    } for index, text in enumerate(patient.alergie, 1)]


def consent_resource(patient: Patient) -> dict | None:
    if not patient.predem_vyslovena_prani:
        return None
    return {
        "resourceType": "Consent",
        "id": fhir_id(patient.patient_id, "adr"),
        "meta": meta(patient.sada),
        "status": "active",
        "scope": concept("http://terminology.hl7.org/CodeSystem/consentscope", "adr", "Advanced Care Directive"),
        "category": [concept("http://terminology.hl7.org/CodeSystem/consentcategorycodes", "acd", "Advance Directive")],
        "patient": ref("Patient", patient.patient_id),
        "policyRule": {"text": "Předem vyslovené přání – informace pro tým, nikdy důvod nedoporučit pomoc"},
        "sourceAttachment": {"contentType": "text/plain", "title": patient.predem_vyslovena_prani},
    }


def baseline_observations(patient: Patient) -> list[dict]:
    pid, dataset, body = patient.patient_id, patient.sada, patient.antropometrie
    start = iso(patient.obdobi_sledovani["od"])

    def observation(key: str, code: str, display: str, category: str, value: dict) -> dict:
        return {
            "resourceType": "Observation",
            "id": fhir_id(pid, "baseline", key),
            "meta": meta(dataset, {"system": "urn:meddi:tag", "code": "baseline"}),
            "status": "final",
            "category": [concept("http://terminology.hl7.org/CodeSystem/observation-category", category)],
            "code": {"coding": [{"system": LOINC, "code": code, "display": display}], "text": display},
            "subject": ref("Patient", pid),
            "effectiveDateTime": start,
            **value,
        }

    def quantity(value: float, unit: str, code: str) -> dict:
        return {"valueQuantity": {"value": value, "unit": unit, "system": UCUM, "code": code}}

    return [
        observation("height", "8302-2", "Body height", "vital-signs", quantity(body.vyska_cm, "cm", "cm")),
        observation("weight", "29463-7", "Body weight", "vital-signs", quantity(body.vaha_kg_vychozi, "kg", "kg")),
        observation("bmi", "39156-5", "Body mass index (BMI) [Ratio]", "vital-signs", quantity(body.bmi, "kg/m2", "kg/m2")),
        observation("ecog", "89247-1", "ECOG Performance Status score", "survey", {"valueInteger": patient.ecog_vychozi}),
    ]


def care_plan_resource(patient: Patient) -> dict:
    pid, treatment = patient.patient_id, patient.lecba
    classes = drug_classes(" ".join([treatment.rezim, *treatment.leky]))
    plan = {
        "resourceType": "CarePlan",
        "id": fhir_id(pid, "plan"),
        "meta": meta(patient.sada, *class_tags(classes)),
        "identifier": [{"system": "urn:meddi:careplan", "value": fhir_id(pid, "plan")}],
        "status": "active",
        "intent": "plan",
        "category": [{"text": treatment.zamer}],
        "title": treatment.rezim,
        "description": "; ".join(treatment.leky) or treatment.rezim,
        "subject": ref("Patient", pid),
        "period": {"start": iso(treatment.cykly[0].datum_d1 if treatment.cykly else patient.obdobi_sledovani["od"])},
        "note": [{"text": treatment.poznamka}] if treatment.poznamka else [],
        "activity": [{"detail": {
            "code": {"text": f"Cyklus {cycle.cyklus}"},
            "status": "scheduled",
            "scheduledPeriod": {"start": iso(cycle.datum_d1)},
            "description": f"C{cycle.cyklus} D1 – {treatment.rezim}",
        }} for cycle in treatment.cykly],
    }
    if treatment.delka_cyklu:
        plan["extension"] = [ext("cycle-length-days", valueInteger=treatment.delka_cyklu)]
    return plan


def medication_request(patient: Patient, index: int, med: Lek) -> dict:
    request = {
        "resourceType": "MedicationRequest",
        "id": fhir_id(patient.patient_id, "med", index),
        "meta": meta(patient.sada, *class_tags(drug_classes(med.lek))),
        "status": "completed" if med.do_data else "active",
        "intent": "order",
        "category": [concept("urn:meddi:lek-typ", med.typ, text=med.typ)],
        "medicationCodeableConcept": {"text": med.lek},
        "subject": ref("Patient", patient.patient_id),
        "reasonCode": [{"text": med.indikace}],
        "dosageInstruction": [{"text": f"{med.davka}, {med.frekvence}", "asNeededBoolean": med.pri_potizich}],
    }
    if med.od_data:
        request["authoredOn"] = med.od_data
    period = {key: value for key, value in (("start", med.od_data), ("end", med.do_data)) if value}
    if period:
        request["dispenseRequest"] = {"validityPeriod": period}
    return request


def lab_observation(patient: Patient, lab: Lab) -> dict:
    loinc = LAB_LOINC.get(lab.kod)
    codings = ([{"system": LOINC, "code": loinc, "display": lab.test}] if loinc else []) + [
        {"system": "urn:meddi:lab", "code": lab.kod, "display": lab.test}]
    flag = {"L": ("L", "Low"), "H": ("H", "High")}.get(lab.priznak, ("N", "Normal"))
    return {
        "resourceType": "Observation",
        "id": fhir_id(lab.odber_id, lab.kod),
        "meta": meta(patient.sada),
        "identifier": [{"system": "urn:meddi:lab", "value": fhir_id(lab.odber_id, lab.kod)}],
        "status": "final",
        "category": [concept("http://terminology.hl7.org/CodeSystem/observation-category", "laboratory")],
        "code": {"coding": codings, "text": lab.test},
        "subject": ref("Patient", patient.patient_id),
        "effectiveDateTime": iso(lab.timestamp),
        "performer": [{"display": lab.misto}],
        "valueQuantity": {"value": lab.hodnota, "unit": lab.jednotka},
        "interpretation": [concept("http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation", *flag)],
        "referenceRange": [{"low": {"value": lab.ref_min, "unit": lab.jednotka},
                            "high": {"value": lab.ref_max, "unit": lab.jednotka}}],
    }


def diagnostic_reports(patient: Patient) -> list[dict]:
    return [{
        "resourceType": "DiagnosticReport",
        "id": fhir_id(patient.patient_id, "exam", index),
        "meta": meta(patient.sada),
        "status": "final",
        "code": {"text": exam.vysetreni},
        "subject": ref("Patient", patient.patient_id),
        "effectiveDateTime": iso(exam.datum),
        "conclusion": exam.vysledek,
    } for index, exam in enumerate(patient.vysetreni, 1)]


def team_event_resources(patient: Patient) -> list[dict]:
    """hospitalizace opens an Encounter, the next propusteni closes it; other types are Communications."""
    pid, dataset = patient.patient_id, patient.sada
    resources: list[dict] = []
    open_encounter: dict | None = None
    for index, event in enumerate(patient.udalosti_tymu, 1):
        event_id = fhir_id(pid, "ev", index)
        if event.typ == "hospitalizace":
            open_encounter = encounter(pid, dataset, event_id, event)
            resources.append(open_encounter)
        elif event.typ == "propusteni":
            target = open_encounter or encounter(pid, dataset, event_id, event, admitted=False)
            target["status"] = "finished"
            target["period"]["end"] = iso(event.timestamp)
            target["hospitalization"] = {"dischargeDisposition": {"text": event.text}}
            if open_encounter is None:
                resources.append(target)
            open_encounter = None
        else:
            resources.append({
                "resourceType": "Communication",
                "id": event_id,
                "meta": meta(dataset, {"system": "urn:meddi:tag", "code": "team-event"}),
                "identifier": [{"system": "urn:meddi:team-event", "value": event_id}],
                "status": "completed",
                "category": [concept("urn:meddi:team-event", event.typ, text=event.typ)],
                "subject": ref("Patient", pid),
                "sent": iso(event.timestamp),
                "sender": {"display": event.autor},
                "payload": [{"contentString": event.text}],
            })
    return resources


def encounter(pid: str, dataset: str, event_id: str, event: TeamEvent, admitted: bool = True) -> dict:
    return {
        "resourceType": "Encounter",
        "id": event_id,
        "meta": meta(dataset),
        "identifier": [{"system": "urn:meddi:team-event", "value": event_id}],
        "status": "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP",
                  "display": "inpatient encounter"},
        "type": [concept("urn:meddi:team-event", "hospitalizace", text="hospitalizace")],
        "subject": ref("Patient", pid),
        "period": {"start": iso(event.timestamp)} if admitted else {},
        "serviceProvider": {"display": event.autor},
        "reasonCode": [{"text": event.text}] if admitted else [],
    }


def patient_resources(patient: Patient) -> list[dict]:
    """Everything the seed writes for one patient. Check-ins are excluded (they arrive by replay)."""
    relations = {relation_of(patient.demografie.vyplnuje)} | {
        relation_of(checkin.vyplnil) for checkin in patient.checkiny}
    resources = [
        patient_resource(patient),
        *[related_person(patient.patient_id, relation, patient.sada) for relation in sorted(relations - {None})],
        *condition_resources(patient),
        *allergy_resources(patient),
        consent_resource(patient),
        *baseline_observations(patient),
        care_plan_resource(patient),
        *[medication_request(patient, index, med) for index, med in enumerate(patient.leky, 1)],
        *[lab_observation(patient, lab) for lab in patient.laboratore],
        *diagnostic_reports(patient),
        *team_event_resources(patient),
    ]
    return [resource for resource in resources if resource]


# ---------- questionnaires ----------

def answer_system(questionnaire_id: str, question_id: str) -> str:
    return f"urn:meddi:answer:{questionnaire_id}:{question_id}"


def questionnaire_resource(definition: dict) -> dict:
    qid = definition["id"]
    items = []
    for question in definition["otazky"]:
        kind = question["typ"]
        item = {"linkId": question["id"], "text": question["text"]}
        if kind in ("jedna", "vice"):
            item["type"] = "choice"
            item["repeats"] = kind == "vice"
            item["answerOption"] = [answer_option(qid, question["id"], index, option)
                                    for index, option in enumerate(question.get("moznosti") or [])]
        elif kind == "text":
            item["type"] = "text"
        else:
            item["type"] = "integer"
        if kind == "skala_1_10":
            item["extension"] = [
                {"url": "http://hl7.org/fhir/StructureDefinition/minValue", "valueInteger": 1},
                {"url": "http://hl7.org/fhir/StructureDefinition/maxValue", "valueInteger": 10},
            ]
        if question.get("podminka"):
            source, option_index = question["podminka"].split(":")
            item["enableWhen"] = [{"question": source, "operator": "=",
                                   "answerCoding": {"system": answer_system(qid, source), "code": option_index}}]
        hints = [hint for hint in (question.get("navod"), question.get("poznamka")) if hint]
        if hints:
            item["item"] = [{"linkId": f"{question['id']}.hint", "type": "display", "text": " ".join(hints)}]
        items.append(item)
    resource = {
        "resourceType": "Questionnaire",
        "id": fhir_id(qid),
        "meta": meta("dev"),
        "url": QUESTIONNAIRE_URL + qid,
        "identifier": [{"system": "urn:meddi:questionnaire", "value": qid}],
        "name": qid,
        "title": definition["nazev"],
        "status": "active",
        "subjectType": ["Patient"],
        "publisher": "MEDDI hub / MOÚ",
        "item": items,
    }
    if definition.get("poznamka"):
        resource["description"] = definition["poznamka"]
    return resource


def answer_option(qid: str, question_id: str, index: int, option: dict) -> dict:
    result = {"valueCoding": {"system": answer_system(qid, question_id), "code": str(index), "display": option["text"]}}
    extensions = colour_warning_extensions(option.get("barva"), option.get("upozorneni"))
    if extensions:
        result["extension"] = extensions
    return result


def colour_warning_extensions(colour: str | None, warning: str | None) -> list[dict]:
    extensions = [ext("answer-colour", valueCode=colour)] if colour else []
    if warning:
        extensions.append(ext("answer-warning", valueString=warning))
    return extensions


def questionnaire_resources(definitions: list[dict]) -> list[dict]:
    return [questionnaire_resource(definition) for definition in definitions]


# ---------- check-in (written by replay / live, never by the seed) ----------

def checkin_resources(patient: Patient, checkin: Checkin) -> list[dict]:
    pid, dataset = patient.patient_id, patient.sada
    author = author_ref(pid, checkin.vyplnil)
    at = iso(checkin.timestamp)
    identifier = [checkin_identifier(checkin.checkin_id)]
    resources: list[dict] = []
    relation = relation_of(checkin.vyplnil)
    if relation:
        resources.append(related_person(pid, relation, dataset))
    if checkin.stav == "nevyplneno":
        resources.append({
            "resourceType": "Task",
            "id": fhir_id(checkin.checkin_id, "missed"),
            "meta": meta(dataset),
            "identifier": identifier,
            "status": "failed",
            "intent": "order",
            "code": concept("urn:meddi:task", "missed-checkin", "Nevyplněný check-in"),
            "description": f"Check-in {checkin.checkin_id} nebyl vyplněn",
            "for": ref("Patient", pid),
            "owner": ref("Patient", pid),
            "authoredOn": at,
        })
    for fill in checkin.dotazniky:
        resources.append(questionnaire_response(patient, checkin, fill, author, at))
    for observation in vital_observations(patient, checkin):
        resources.append(observation)
    if checkin.zprava_pacienta:
        resources.append({
            "resourceType": "Communication",
            "id": fhir_id(checkin.checkin_id, "msg"),
            "meta": meta(dataset),
            "language": patient.demografie.jazyk,
            "identifier": identifier,
            "status": "completed",
            "category": [concept("urn:meddi:communication", "patient-message", "Zpráva pacienta")],
            "subject": ref("Patient", pid),
            "sender": author,
            "sent": at,
            "payload": [{"contentString": checkin.zprava_pacienta}],
        })
    for index, note in enumerate(checkin.prilohy, 1):
        resources.append({
            "resourceType": "DocumentReference",
            "id": fhir_id(checkin.checkin_id, "att", index),
            "meta": meta(dataset),
            "identifier": identifier,
            "status": "current",
            "type": {"text": "Fotografie – textový popis"},
            "subject": ref("Patient", pid),
            "date": at,
            "author": [author],
            "description": note,
            "content": [{"attachment": {
                "contentType": "text/plain; charset=utf-8",
                "title": note.split(" – ")[0],
                "data": base64.b64encode(note.encode("utf-8")).decode("ascii"),
            }}],
        })
    return resources


def questionnaire_response(patient: Patient, checkin: Checkin, fill, author: dict, at: str) -> dict:
    items = []
    for answer in fill.odpovedi:
        answers = []
        indexes, values = answer.odpoved_index, answer.odpoved
        if isinstance(indexes, list):
            labels = values if isinstance(values, list) else [values] * len(indexes)
            answers = [coded_answer(fill.dotaznik_id, answer.otazka_id, index, label)
                       for index, label in zip(indexes, labels)]
        elif indexes is not None:
            answers = [coded_answer(fill.dotaznik_id, answer.otazka_id, indexes, values)]
        elif isinstance(values, int):
            answers = [{"valueInteger": values}]
        elif isinstance(values, str) and values:
            answers = [{"valueString": values}]
        if not answers:
            continue
        extensions = colour_warning_extensions(answer.barva, answer.upozorneni)
        if extensions:
            for item_answer in answers:
                item_answer["extension"] = extensions
        items.append({"linkId": answer.otazka_id, "text": answer.otazka, "answer": answers})
    extensions = [ext("checkin-id", valueString=checkin.checkin_id)]
    if fill.nejvyssi_barva:
        extensions.append(ext("highest-colour", valueCode=fill.nejvyssi_barva))
    extensions += [ext("shown-warning", valueString=warning) for warning in fill.zobrazena_upozorneni]
    if checkin.cyklus is not None:
        extensions.append(ext("cycle", valueInteger=checkin.cyklus))
    if checkin.den_cyklu is not None:
        extensions.append(ext("cycle-day", valueInteger=checkin.den_cyklu))
    return {
        "resourceType": "QuestionnaireResponse",
        "id": fhir_id(fill.vyplneni_id),
        "meta": meta(patient.sada),
        "extension": extensions,
        "identifier": checkin_identifier(checkin.checkin_id),
        "questionnaire": QUESTIONNAIRE_URL + fill.dotaznik_id,
        "status": "completed",
        "subject": ref("Patient", patient.patient_id),
        "authored": at,
        "author": author,
        "source": author,
        "item": items,
    }


def coded_answer(qid: str, question_id: str, index: int, label) -> dict:
    return {"valueCoding": {"system": answer_system(qid, question_id), "code": str(index), "display": str(label)}}


def vital_observations(patient: Patient, checkin: Checkin) -> list[dict]:
    vitals = checkin.vitalni_funkce or {}
    at = iso(checkin.timestamp)

    def base(key: str, code: str, display: str, source: str) -> dict:
        return {
            "resourceType": "Observation",
            "id": fhir_id(checkin.checkin_id, key),
            "meta": meta(patient.sada),
            "identifier": [checkin_identifier(checkin.checkin_id)],
            "status": "final",
            "category": [concept("http://terminology.hl7.org/CodeSystem/observation-category", "vital-signs")],
            "code": {"coding": [{"system": LOINC, "code": code, "display": display}], "text": display},
            "subject": ref("Patient", patient.patient_id),
            "effectiveDateTime": at,
            "performer": [author_ref(patient.patient_id, checkin.vyplnil)],
            "device": {"display": source},
        }

    def quantity(value: float, unit: str, code: str) -> dict:
        return {"value": value, "unit": unit, "system": UCUM, "code": code}

    observations = []
    for key, (code, display, ucum, unit) in VITALS.items():
        if key in vitals:
            observation = base(key, code, display, vitals[key].zdroj)
            observation["valueQuantity"] = quantity(vitals[key].hodnota, unit, ucum)
            observations.append(observation)
    pressure = [(key, code, display) for key, code, display in (
        ("tk_sys", "8480-6", "Systolic blood pressure"), ("tk_dia", "8462-4", "Diastolic blood pressure"))
        if key in vitals]
    if pressure:
        observation = base("bp", "85354-9", "Blood pressure panel with all children optional", vitals[pressure[0][0]].zdroj)
        observation["component"] = [{
            "code": {"coding": [{"system": LOINC, "code": code, "display": display}], "text": display},
            "valueQuantity": quantity(vitals[key].hodnota, "mmHg", "mm[Hg]"),
        } for key, code, display in pressure]
        observations.append(observation)
    return observations


# ---------- navigator outputs ----------

def risk_assessment(output: TriageOutput, dataset: str, basis: list[str]) -> dict:
    level = output.uroven
    extensions = [ext("triage-rule", valueString=rule) for rule in output.pravidla]
    extensions += [ext("warning-sign", valueString=sign) for sign in output.varovne_priznaky]
    extensions += [ext("confidence", valueCode=output.jistota), ext("notify-team", valueBoolean=output.upozornit_tym),
                   ext("source", valueCode=output.zdroj)]
    if output.doporuceny_kontakt:
        extensions.append(ext("contact", valueString=output.doporuceny_kontakt))
    if output.sla_do:
        extensions.append(ext("sla", valueDateTime=iso(output.sla_do)))
    if output.doplnujici_otazka:
        extensions.append(ext("follow-up-question", valueString=output.doplnujici_otazka))
    prediction = {
        "outcome": concept("urn:meddi:step", output.doporuceny_krok, text=output.doporuceny_krok),
        "qualitativeRisk": concept("urn:meddi:triage-level", str(level), LEVEL_NAMES[level],
                                   f"{level} – {LEVEL_NAMES[level]}"),
    }
    if output.klicove_nalezy:
        prediction["rationale"] = "; ".join(output.klicove_nalezy)
    return {
        "resourceType": "RiskAssessment",
        "id": fhir_id(output.checkin_id, "risk"),
        "meta": meta(dataset),
        "extension": extensions,
        "identifier": [checkin_identifier(output.checkin_id)],
        "status": "final",
        "code": concept("urn:meddi:triage", "meddi-triage", "MEDDI triáž"),
        "method": concept("urn:meddi:engine", output.verze, text=output.verze),
        "subject": ref("Patient", output.patient_id),
        "occurrenceDateTime": iso(output.as_of),
        "performer": ref("Device", DEVICE_ID, "MEDDI navigátor"),
        "basis": [{"reference": reference} for reference in basis],
        "prediction": [prediction],
        "mitigation": output.doporuceni_pro_pacienta,
        "note": [{"text": output.zduvodneni}],
    }


def grade_observations(output: TriageOutput, dataset: str) -> list[dict]:
    """Findings written in the mentor notation („Průjem G2 (pacient)“) become survey Observations."""
    observations = []
    for index, finding in enumerate(output.klicove_nalezy, 1):
        match = GRADE_FINDING.search(finding)
        if not match:
            continue
        observation = {
            "resourceType": "Observation",
            "id": fhir_id(output.checkin_id, "grade", index),
            "meta": meta(dataset, {"system": "urn:meddi:tag", "code": "symptom-grade"}),
            "identifier": [checkin_identifier(output.checkin_id)],
            "status": "final",
            "category": [concept("http://terminology.hl7.org/CodeSystem/observation-category", "survey")],
            "code": {"text": match.group(0).strip()},
            "subject": ref("Patient", output.patient_id),
            "effectiveDateTime": iso(output.as_of),
            "valueInteger": int(match.group("grade")),
            "note": [{"text": finding}],
        }
        if match.group("source"):
            observation["method"] = {"text": match.group("source")}
        observations.append(observation)
    return observations


def reply_communication(output: TriageOutput, dataset: str, in_response_to: str | None) -> dict:
    payload = [{"contentString": output.doporuceni_pro_pacienta}]
    communication = {
        "resourceType": "Communication",
        "id": fhir_id(output.checkin_id, "reply"),
        "meta": meta(dataset),
        "language": output.lang,
        "extension": [ext("triage-level", valueInteger=output.uroven)],
        "identifier": [checkin_identifier(output.checkin_id)],
        "status": "completed",
        "category": [concept("urn:meddi:communication", "navigator-reply", "Odpověď navigátoru")],
        "subject": ref("Patient", output.patient_id),
        "sender": ref("Device", DEVICE_ID, "MEDDI navigátor"),
        "recipient": [ref("Patient", output.patient_id)],
        "sent": iso(output.as_of),
        "payload": payload,
    }
    if in_response_to:
        communication["inResponseTo"] = [{"reference": in_response_to}]
    return communication


def chat_communication(patient: Patient | None, patient_id: str, message: dict, dataset: str,
                       in_response_to: str | None) -> dict:
    navigator = message.get("role") == "navigator"
    author = message.get("author") or "pacient"
    if navigator:
        sender = ref("Device", DEVICE_ID, "MEDDI navigátor")
    elif author in ("pacient", "patient"):
        sender = ref("Patient", patient_id)
    else:
        relation = caregiver_relation(patient)
        sender = ref("RelatedPerson", related_person_id(patient_id, relation), relation)
    at = message.get("at") or datetime.now().astimezone()
    communication = {
        "resourceType": "Communication",
        "id": fhir_id(patient_id, "chat", message.get("id") or hashlib.sha1(str(message).encode()).hexdigest()[:12]),
        "meta": meta(dataset),
        "identifier": [{"system": "urn:meddi:chat", "value": str(message.get("id", ""))}],
        "status": "completed",
        "category": [concept("urn:meddi:communication", "chat", "Chat s navigátorem")],
        "subject": ref("Patient", patient_id),
        "sender": sender,
        "recipient": [ref("Patient", patient_id)] if navigator else [ref("Device", DEVICE_ID)],
        "sent": at if isinstance(at, str) else iso(at),
        "payload": [{"contentString": message.get("text") or ""}],
    }
    if message.get("lang"):
        communication["language"] = message["lang"]
    card = message.get("level_card") or {}
    if card.get("uroven"):
        communication["extension"] = [ext("triage-level", valueInteger=int(card["uroven"]))]
    if message.get("followup_question"):
        communication["payload"].append({"contentString": message["followup_question"]})
    if in_response_to:
        communication["inResponseTo"] = [{"reference": in_response_to}]
    return communication


def caregiver_relation(patient: Patient | None) -> str:
    if patient:
        for filled_by in [patient.demografie.vyplnuje, *(checkin.vyplnil for checkin in patient.checkiny)]:
            relation = relation_of(filled_by)
            if relation:
                return relation
    return "pečující"


def provenance(targets: list[str], entities: list[str], dataset: str, version: str, recorded: datetime,
               activity: str) -> dict:
    agent = f"MEDDI navigátor ({version}; {settings.llm_model})" if settings.llm_enabled else f"MEDDI navigátor ({version})"
    return {
        "resourceType": "Provenance",
        "id": fhir_id(targets[0].split("/", 1)[1], "prov"),
        "meta": meta(dataset),
        "target": [{"reference": target} for target in targets],
        "recorded": iso(recorded),
        "activity": {"text": activity},
        "agent": [{
            "type": concept("http://terminology.hl7.org/CodeSystem/provenance-participant-type", "author", "Author"),
            "who": ref("Device", DEVICE_ID, agent),
        }],
        "entity": [{"role": "source", "what": {"reference": entity}} for entity in entities],
    }


PRIORITY_RANK = {"routine": 0, "urgent": 1, "stat": 2}


def alert_task(task: QueueTask, output: TriageOutput | None, dataset: str, task_id: str,
               extra_notes: list[dict] = (), extra_identifiers: list[dict] = (), now: datetime | None = None) -> dict:
    identifiers = [{"system": "urn:meddi:task", "value": task.id}, *extra_identifiers]
    if task.checkin_id:
        identifiers.append(checkin_identifier(task.checkin_id))
    unique_identifiers = list({(item.get("system"), item.get("value")): item for item in identifiers}.values())
    notes = [*extra_notes, *({"time": iso(note.at), "authorString": note.author, "text": note.text}
                             for note in task.notes)]
    unique_notes = list({(note.get("time"), note.get("text")): note for note in notes}.values())
    resource = {
        "resourceType": "Task",
        "id": task_id,
        "meta": meta(dataset),
        "extension": [ext("triage-level", valueInteger=task.uroven), ext("out-of-hours", valueBoolean=task.out_of_hours)],
        "identifier": unique_identifiers,
        "status": task.status,
        "intent": "order",
        "priority": task.priority,
        "code": concept("urn:meddi:task", "triage-alert", "Upozornění z triáže",
                        f"{LEVEL_NAMES[task.uroven]} · úroveň {task.uroven}"),
        "description": task.why,
        "for": ref("Patient", task.patient_id),
        "authoredOn": iso(task.created),
        "lastModified": iso(now or datetime.now().astimezone()),
        "requester": ref("Device", DEVICE_ID, "MEDDI navigátor"),
        "owner": {"display": task.owner},
        "note": unique_notes,
    }
    if task.sla_do:
        resource["restriction"] = {"period": {"end": iso(task.sla_do)}}
    if output:
        resource["reasonReference"] = ref("RiskAssessment", fhir_id(output.checkin_id, "risk"))
    return resource


def alert_flag(task: QueueTask, dataset: str, task_id: str) -> dict:
    return {
        "resourceType": "Flag",
        "id": fhir_id(task.patient_id, "alert"),
        "meta": meta(dataset),
        "extension": [{"url": "http://hl7.org/fhir/StructureDefinition/flag-detail",
                       "valueReference": ref("Task", task_id)}],
        "status": "inactive" if task.status == "completed" else "active",
        "category": [concept("http://terminology.hl7.org/CodeSystem/flag-category", "clinical", "Clinical")],
        "code": {"text": f"MEDDI navigátor: {LEVEL_NAMES[task.uroven]} – {task.why}"},
        "subject": ref("Patient", task.patient_id),
        "period": {"start": iso(task.created)},
        "author": ref("Device", DEVICE_ID, "MEDDI navigátor"),
    }


def composition(summary: DoctorSummary, dataset: str) -> dict:
    sections = [{"title": title, "text": narrative(getattr(summary, field))}
                for field, title in SECTION_TITLES if getattr(summary, field)]
    return {
        "resourceType": "Composition",
        "id": fhir_id(summary.patient_id, "summary", summary.as_of.strftime("%Y%m%d%H%M")),
        "meta": meta(dataset),
        "extension": [ext("summary-reason", valueString=summary.reason),
                      ext("generated-by", valueCode=summary.generated_by)],
        "text": narrative(summary.text),
        "status": "final",
        "type": concept(LOINC, "60591-5", "Patient summary Document", "Souhrn pro lékaře (30 s)"),
        "subject": ref("Patient", summary.patient_id),
        "date": iso(summary.as_of),
        "author": [ref("Device", DEVICE_ID, "MEDDI navigátor")],
        "title": summary.header,
        "section": sections,
    }
