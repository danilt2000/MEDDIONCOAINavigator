# FHIR and IRIS data layer

How MEDDI JSON and the navigator outputs land in InterSystems IRIS for Health (spec §6, §7, §12). Code: `backend/app/fhir/`,
DDL: `iris/sql/meddi_tables.sql`, tests: `backend/tests/fhir/`.

## Run it

```bash
cd backend
# FHIR seed: Questionnaires + Device + one transaction Bundle per patient (no check-ins), then the MEDDI.* SQL tables
PYTHONPATH=. PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.fhir.seed --datasets dev,rozsirena
#   --reset   first deletes every resource tagged with those datasets, INCLUDING check-ins and outputs written by replay
#   --no-sql  skip the SQL tables
PYTHONPATH=. PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m app.fhir.sql_tables     # SQL tables and views only
PYTHONPATH=. PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest tests/fhir -q     # live test skips when IRIS is down
```

The seed takes about 15 s and is idempotent: every resource has a deterministic id and is written with `PUT`, so a
second run only adds versions. Verified result (FHIR `_summary=count` per `_tag`):

| Dataset | Patient | RelatedPerson | Condition | AllergyIntolerance | Consent | Observation | CarePlan | MedicationRequest | DiagnosticReport | Encounter | Communication |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dev | 14 | 3 | 30 | 1 | 1 | 401 | 14 | 73 | 3 | 5 | 27 |
| rozsirena | 100 | 21 | 215 | 8 | 7 | 2891 | 100 | 523 | 21 | 36 | 193 |

Plus 4 Questionnaires and `Device/meddi-navigator`. 114 patients are readable over FHIR.

## Python API

```python
from app.fhir import fhir_available, write_checkin, write_alert, write_summary, write_chat, flush
write_checkin(patient, checkin, output)   # check-in resources + RiskAssessment, grade Observations, reply, Provenance
write_alert(task, output)                 # Task + Flag + Provenance; updates the patient's open alert Task if one exists
write_summary(summary)                    # Composition + Provenance
write_chat(patient_id, message)           # Communication (+ Provenance for navigator messages); ChatMessage dict
```

- Writers return immediately. One background thread does the work in order (thread-safe, one IRIS licence unit),
  skips it when IRIS is down (`fhir_available()` is cached 30 s up / 10 s down) and logs instead of raising.
  `flush()` waits for the queue (tests, CLIs).
- A patient that is not in FHIR yet (e.g. a hidden-set patient posted live) gets its full record written before its
  first check-in.
- `write_checkin` also upserts a row into `MEDDI.Triage_Result`.
- Throughput: all 1 320 check-ins with outputs drain in about 110 s (about 85 ms per transaction); enqueueing takes milliseconds.
- `write_chat` accepts an optional `message["triage"]` (TriageOutput or dict) and then stores a RiskAssessment for the chat turn.
- `app.fhir.client` has `get`, `search`, `count`, `transaction`, `sql_connection()` for readers (one shared httpx client, keeps the session cookie).

## Conventions

| What | Value |
|---|---|
| Tags on every resource | `urn:meddi:tag|synthetic` + `urn:meddi:dataset|dev` or `|rozsirena` (Questionnaires and Device: `dev`). Extra tags: `urn:meddi:drug-class|<class>` on MedicationRequest and CarePlan, `urn:meddi:tag|baseline`, `|team-event`, `|symptom-grade` |
| Ids | built from MEDDI ids: `Patient/ONC-001`, `Observation/ONC-001-L01-leu`, `QuestionnaireResponse/ONC-001-C07-NU`, `RiskAssessment/ONC-001-C07-risk`; characters outside `[A-Za-z0-9.-]` become `-` |
| Identifiers | `urn:meddi:patient|ONC-001`; every check-in-derived resource carries `urn:meddi:checkin|<checkin_id>` |
| Extensions | `urn:meddi:fhir:ext:<name>` (household, digital-literacy, filled-by, answer-colour, answer-warning, highest-colour, shown-warning, cycle, cycle-day, triage-rule, warning-sign, confidence, contact, sla, triage-level, …) |
| Code systems | LOINC, ICD-10 (`http://hl7.org/fhir/sid/icd-10`), HL7 terminology; ours: `urn:meddi:lab`, `urn:meddi:lek-typ`, `urn:meddi:team-event`, `urn:meddi:triage-level`, `urn:meddi:step`, `urn:meddi:task`, `urn:meddi:answer:<questionnaire>:<question>` |
| Times | `datum` + `cas` in Europe/Prague with offset, e.g. `2026-09-09T21:52:00+02:00` |

## Mapping (spec §7)

| MEDDI JSON | FHIR R4 (id) | Notes |
|---|---|---|
| `demografie` | Patient (`ONC-001`) | name from `jmeno_fiktivni`; gender; `birthDate` = year of start − age, flagged by `_birthDate` extension `birthdate-approximate`; `communication.language` cs/sk; `address.state` = kraj; extensions household, digital-literacy, filled-by, age-at-start |
| `vyplnuje`, `vyplnil` ≠ pacient | RelatedPerson (`ONC-010-dcera`) | v3-RoleCode DAU / WIFE / HUSB / SON / FAMMEMB; author of QuestionnaireResponse, Communication, DocumentReference |
| `diagnoza` | Condition (`-dx`) | ICD-10 `mkn10`, `stage.summary.text`, biomarkers in `note`, `onsetDateTime` |
| `komorbidity[]` | Condition (`-cm-N`) | category problem-list-item, text |
| `alergie[]` | AllergyIntolerance (`-allergy-N`) | text |
| `predem_vyslovena_prani` | Consent (`-adr`) | scope adr, category acd, text in `sourceAttachment.title` |
| `antropometrie`, `ecog_vychozi` | Observation (`-baseline-height/weight/bmi/ecog`) | 8302-2, 29463-7, 39156-5, 89247-1; effective = start of monitoring |
| `lecba` + `cykly[]` | CarePlan (`-plan`) | title = rezim, category = zamer, description = lecba.leky, note = poznamka, extension cycle-length-days, one `activity` per cycle (`scheduledPeriod.start` = D1), drug-class tags |
| `leky[]` | MedicationRequest (`-med-N`) | category `urn:meddi:lek-typ` = typ; `dosageInstruction.text` = davka + frekvence; `asNeededBoolean` = pri_potizich; `reasonCode` = indikace; validity od/do; drug-class tags |
| `laboratore[]` | Observation laboratory (`<odber_id>-<kod>`) | LOINC from `kod` (+ `urn:meddi:lab` coding), value + unit as in the data, `referenceRange`, interpretation L/H/N |
| `vysetreni[]` | DiagnosticReport (`-exam-N`) | `conclusion` = vysledek, date only |
| `udalosti_tymu[]` hospitalizace / propusteni | Encounter (`-ev-N`) | class IMP; hospitalizace opens it, the next propusteni closes it (`period.end`, `dischargeDisposition`) |
| other `udalosti_tymu[]` | Communication (`-ev-N`) | category `urn:meddi:team-event|<typ>`, `sent`, sender display = autor |
| `dotazniky_definice.json` | Questionnaire ×4 (`nezadouci-ucinky`, `psychoonkologicky-screening`, `bolest-analgeticka-terapie`, `esas`) | url `urn:meddi:questionnaire:<id>`; jedna/vice → choice (vice repeats), text → text, scales/numbers → integer (1–10 min/max); answerOption valueCoding code = option index with answer-colour / answer-warning extensions; `podminka "ucinky:1"` → `enableWhen` on `ucinky` = code 1; `navod` as a display child item |
| check-in `dotazniky[]` | QuestionnaireResponse (`<vyplneni_id>`) | authored = check-in time, author/source Patient or RelatedPerson, answers as valueCoding (index) / valueInteger / valueString with colour and warning extensions; extensions checkin-id, highest-colour, shown-warning, cycle, cycle-day |
| `vitalni_funkce` | Observation vital-signs (`<checkin>-teplota-c`, `-bp`, …) | 8310-5, 85354-9 panel (8480-6 / 8462-4), 8867-4, 9279-1, 59408-5, 29463-7, 14743-9; UCUM units; `device.display` = zdroj |
| `zprava_pacienta` | Communication (`<checkin>-msg`) | category patient-message, sender Patient/RelatedPerson, `language`, payload text |
| `prilohy[]` | DocumentReference (`<checkin>-att-N`) | `description` = note, text attachment |
| `stav: nevyplneno` | Task (`<checkin>-missed`) | code `urn:meddi:task|missed-checkin`, status failed |
| triage result | RiskAssessment (`<checkin>-risk`) | `prediction.qualitativeRisk` = level 1–4, `prediction.outcome` = step, `basis` → the check-in resources, `note` = zduvodneni, `mitigation` = patient advice, `method` = engine version, extensions rules / warning signs / confidence / contact / sla |
| symptom grade | Observation survey (`<checkin>-grade-N`) | from findings in mentor notation: code.text „Průjem G2 (pacient)“, valueInteger = grade, method = source |
| patient reply | Communication (`<checkin>-reply`) | sender `Device/meddi-navigator`, `inResponseTo` the patient's message |
| alert | Task (store task id) + Flag (`<patient>-alert`) | priority routine/urgent/stat, owner display, `restriction.period.end` = SLA, `reasonReference` → RiskAssessment, notes; a new escalation updates the patient's open Task (max priority, identifiers and notes merged); Flag `flag-detail` → Task |
| doctor summary | Composition (`<patient>-summary-<yyyymmddhhmm>`) | LOINC 60591-5, sections Proč teď / K rozhodnutí, Léčba, Vývoj, Laboratoř, Nehlásí, K posouzení |
| chat | Communication (`<patient>-chat-<message id>`) | navigator messages: sender Device, `inResponseTo` the last user message, triage-level extension |
| every AI output | Provenance (`<target>-prov`) | agent `Device/meddi-navigator` with engine + model version, entities = inputs |

## FHIR searches for the demo

All under `http://localhost:52773/fhir/r4` (Basic `SuperUser`/`SYS`).

```text
Patient?_tag=urn:meddi:tag|synthetic&_summary=count                 → 114
Patient?identifier=urn:meddi:patient|ONC-018
Patient/ONC-001/$everything
Observation?patient=ONC-001&code=http://loinc.org|751-8&_sort=date   neutrophils, nadir 0.3 on 9. 9.
Observation?patient=ONC-007&code=http://loinc.org|29463-7&_sort=date weight trend (after replay)
QuestionnaireResponse?identifier=urn:meddi:checkin|ONC-001-C07
RiskAssessment?patient=ONC-004&_sort=date
Task?code=urn:meddi:task|triage-alert&status=requested,accepted,in-progress
Flag?status=active
Questionnaire/nezadouci-ucinky
```

## SQL over the FHIR repository

The JsonAdvSQL storage keeps every resource as JSON in `HSFHIR_X0001_R.Rsrc` (`ResourceType`, `ResourceId`,
`ResourceString`, `Deleted`) and search indexes in `HSFHIR_X0001_S.<Type>` plus `HSFHIR_X0001_S_<Type>.<param>`
(e.g. `HSFHIR_X0001_S_Observation.code`, `HSFHIR_X0001_S_Rsrc._tag`). `iris/sql/meddi_tables.sql` projects it into
three views with `JSON_TABLE` (created by `app.fhir.sql_tables`):

- `MEDDI.FHIR_Observation` (PatientRef, EffectiveAt, Category, Loinc, Display, NumValue, IntValue, Unit, Systolic, Diastolic, Device, Interpretation)
- `MEDDI.FHIR_Risk` (PatientRef, CheckinId, OccurredAt, TriageLevel, Step, EngineVersion, Rationale)
- `MEDDI.FHIR_Task` (PatientRef, Code, Status, Priority, Description, OwnerName, AuthoredOn, SlaEnd)

Queries (namespace FHIRSERVER), all run against the live IRIS; per-patient series fill in as replay writes check-ins:

```sql
-- weight trend of one patient (vitals arrive with replay; 83.4 → 86.4 kg for the ONC-007 heart-failure course)
SELECT EffectiveAt, NumValue AS kg, Device FROM MEDDI.FHIR_Observation
WHERE PatientRef = 'Patient/ONC-007' AND Loinc = '29463-7' ORDER BY EffectiveAt;

-- the same straight from JSON_TABLE, no view
SELECT j.measured, j.kg
FROM HSFHIR_X0001_R.Rsrc r, JSON_TABLE(r.ResourceString, '$' COLUMNS (
    patient VARCHAR(40) PATH '$.subject.reference', measured VARCHAR(40) PATH '$.effectiveDateTime',
    loinc VARCHAR(20) PATH '$.code.coding[0].code', kg NUMERIC(6,1) PATH '$.valueQuantity.value')) j
WHERE r.ResourceType = 'Observation' AND r.Deleted = 0 AND j.loinc = '29463-7' AND j.patient = 'Patient/ONC-007'
ORDER BY j.measured;

-- the same through the FHIR search index tables (dates are stored in UTC, values as a ±precision range)
SELECT o.date_Start, (v.value_ValueLow + v.value_ValueHigh) / 2 AS kg
FROM HSFHIR_X0001_S.Observation o
JOIN HSFHIR_X0001_S_Observation.code c ON c.Key = o.Key
JOIN HSFHIR_X0001_S_Observation.valueQuantity v ON v.Key = o.Key
WHERE c.value_System = 'http://loinc.org' AND c.value_Value = '29463-7' AND o.patient_RelativeRef = 'Patient/ONC-007'
ORDER BY o.date_Start;

-- fever readings across all patients
SELECT PatientRef, EffectiveAt, NumValue AS celsius, Device FROM MEDDI.FHIR_Observation
WHERE Loinc = '8310-5' AND NumValue >= 38 ORDER BY EffectiveAt;

-- blood pressure series
SELECT EffectiveAt, Systolic, Diastolic FROM MEDDI.FHIR_Observation
WHERE PatientRef = 'Patient/ONC-009' AND Loinc = '85354-9' ORDER BY EffectiveAt;

-- low neutrophils (33 rows on the seed)
SELECT PatientRef, EffectiveAt, NumValue FROM MEDDI.FHIR_Observation
WHERE Loinc = '751-8' AND Interpretation = 'L' ORDER BY PatientRef, EffectiveAt;

-- triage levels and open alerts
SELECT TriageLevel, COUNT(*) FROM MEDDI.FHIR_Risk GROUP BY TriageLevel;
SELECT PatientRef, Priority, OwnerName, SlaEnd FROM MEDDI.FHIR_Task
WHERE Code = 'triage-alert' AND Status <> 'completed' ORDER BY SlaEnd;

-- which rule fired, joined to the rule table
SELECT t.CheckinId, t.TriageLevel, r.RuleId, r.Expr FROM MEDDI.Triage_Result t
JOIN MEDDI.Triage_Rule r ON t.RuleIds [ r.RuleId WHERE t.PatientId = 'ONC-004';

-- evaluation (app.eval / demo operator only): predicted vs expected
SELECT e.TriageLevel AS expected, t.TriageLevel AS predicted, COUNT(*) FROM MEDDI.Eval_Expected e
JOIN MEDDI.Triage_Result t ON t.CheckinId = e.CheckinId GROUP BY e.TriageLevel, t.TriageLevel;
```

FHIR SQL Builder (the official projection tool) works through the UI at `/csp/fhir-management` → FHIR SQL Builder:
credentials `SuperUser`/`SYS`, repository host `localhost` port 52773 → Discover `/fhir/r4`, Analysis, Transform
Spec, Projection into a package (kit tutorial 3.5). Not scripted here: the only scripting wrapper is an experimental
third-party repo; the views above give the same SQL access without it.

## Engine tables (IRIS SQL, schema MEDDI)

| Table | Filled by | Rows now |
|---|---|---|
| `Triage_Rule (RuleId, MinLevel, Area, Expr, PatientHint, Source, Active)` | `rules.yaml` (label → Expr, hint_cs → PatientHint) | 47 |
| `Drug_Class (Drug, Class)` | drug-name stems found in both packages (§8.4 classes, regimen acronyms expanded) | 33 |
| `Triage_Result (CheckinId, PatientId, AsOf, TriageLevel, Step, Contact, NotifyTeam, RuleIds, Confidence, EngineVersion, Source)` | `write_checkin` | grows with replay |
| `Eval_Expected (CheckinId, Dataset, TriageLevel, Step, NotifyTeam, Contact)` | ground truth, read only by `app.eval` | 1 320 |
| `Eval_Run (RunId, CheckinId, Expected, Predicted, StepOk, ContactOk, NotifyOk)` | `app.eval` | — |

`LEVEL` is a reserved word in IRIS SQL, so the spec's `Level` columns are `TriageLevel`.

## Portal and URLs

| What | URL |
|---|---|
| Management portal | http://localhost:52773/csp/sys/UtilHome.csp (`SuperUser` / `SYS`) |
| SQL explorer (FHIRSERVER) | http://localhost:52773/csp/sys/exp/%25CSP.UI.Portal.SQL.Home.zen?$NAMESPACE=FHIRSERVER |
| FHIR base / metadata | http://localhost:52773/fhir/r4 , http://localhost:52773/fhir/r4/metadata |
| FHIR server management, SQL Builder | http://localhost:52773/csp/fhir-management/index.html |
| Swagger UI | http://localhost:52773/fhir/swagger-ui/index.html |

## IRIS facts found while building this

- A search that matches more than 1000 resources fails with HTTP 413 `SearchTooCostly`, whatever `_count` is
  (`_summary=count` still works). Always filter by patient for FHIR reads; for bulk use SQL. `seed --reset` lists keys
  through `HSFHIR_X0001_S_Rsrc._tag` for this reason. The cap is the endpoint setting `MaxSearchResults` (1000).
- The server validates property names (unknown element → 400) but not reference targets: a dangling reference is accepted.
- `PUT Type/id` creates with our own id, also inside a transaction; a deleted resource returns 410 and can be re-created by PUT.
- `JSON_TABLE` works on `HSFHIR_X0001_R.Rsrc.ResourceString`; `NESTED PATH` is not supported (use `component[0]`, `component[1]`).
- Search-table timestamps (`date_Start`) are UTC; the JSON keeps the original offset.
