# InterSystems IRIS for Health in the MEDDI navigator

IRIS is the system of record and the AI data platform of the navigator: every patient record, check-in, triage result,
alert, summary and chat turn is stored as FHIR R4; SQL tables and views over the same data drive trends and metrics;
Vector Search feeds the navigator chat; an interoperability production brings HL7v2 labs in and sends alerts out; an
MCP server gives agents safe, logged tools. This page lists every feature we use and exactly where in the code.

## Instance

| | |
|---|---|
| Container | `meddi-iris` (`docker-compose.yml`, image built from `iris/Dockerfile` on `intersystems/irishealth-community`) |
| Setup | `iris/setup.script`: Foundation namespace `FHIRSERVER`, FHIR endpoint `/fhir/r4` (`HS.FHIRServer.Storage.JsonAdvSQL.InteractionsStrategy`, `hl7.fhir.r4.core@4.0.1`), `MaxSearchResults` raised from 1 000 to 100 000; `iris/merge.cpf` enables `%Service_CallIn` for the Python native API |
| Production | `sh iris/scripts/install.sh` loads `iris/src/MEDDI/**.cls` and starts `MEDDI.Production` with auto-start |
| Login | `SuperUser` / `SYS` |
| Ports | 52773 web (portal, FHIR REST), 1972 superserver (DB-API, native API) |
| Python settings | `backend/app/config.py` (`iris_host`, `iris_port`, `iris_namespace`, `fhir_base`, …) |
| Licence care | Community Edition allows ~8 concurrent units: one shared `httpx.Client` with cookies (`app/fhir/client.py::client`), one DB-API connection per writer thread, short-lived connections elsewhere |
| Health | `GET /api/health` (`app/api/meta.py::health`): superserver port, FHIR `metadata`, MCP port |

Portal links (log in as `SuperUser`/`SYS`):

- Management portal: http://localhost:52773/csp/sys/UtilHome.csp
- SQL explorer (namespace FHIRSERVER): http://localhost:52773/csp/sys/exp/%25CSP.UI.Portal.SQL.Home.zen?$NAMESPACE=FHIRSERVER
- Production: http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.ProductionConfig.zen?PRODUCTION=MEDDI.Production
- Message viewer (traces): http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.MessageViewer.zen
- Event log: http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.EventLog.zen
- FHIR server management and FHIR SQL Builder: http://localhost:52773/csp/fhir-management/index.html
- FHIR REST base: http://localhost:52773/fhir/r4 (Basic auth)

## 1. FHIR R4 repository

| What | Where |
|---|---|
| REST client (GET, search, count, transaction, PUT entries, tagged delete) | `backend/app/fhir/client.py` |
| MEDDI JSON → FHIR mapping (spec §7, table in `docs/fhir-mapping.md`) | `backend/app/fhir/mappers.py` |
| Seed of both datasets, idempotent (fixed ids from the MEDDI ids, PUT in transaction Bundles, `--reset` by dataset tag) | `backend/app/fhir/seed.py`, `scripts/seed.sh` |
| Live writes from the API (background queue, never blocks or raises) | `backend/app/fhir/writers.py`: `write_checkin`, `write_alert`, `write_summary`, `write_chat`, `flush` |
| Callers | `app/services/side_effects.py` (check-ins, alerts, summaries), `app/agent/navigator.py` (chat), `app/store.py::_write_history_to_fhir` (`DEMO_WRITE_FHIR=1`) |

Resources (all tagged `synthetic` plus `dev`/`rozsirena`):

- Patient record: `Patient`, `RelatedPerson`, `Condition`, `AllergyIntolerance`, `Consent` (advance directive), `CarePlan`
  (regimen, cycles), `MedicationRequest` (with drug-class tags), lab `Observation` (LOINC), `DiagnosticReport`,
  `Encounter`, `Communication` (team events), baseline vitals.
- Shared: 4 `Questionnaire`s (MEDDI questionnaires, `podminka` → `enableWhen`), `Device` „MEDDI navigátor“.
- Each check-in: `QuestionnaireResponse` (author = patient or `RelatedPerson`), vital-sign `Observation`s, the message
  as `Communication`, a missed check-in as `Task`.
- Each AI output: `RiskAssessment` (level, rules, quoted evidence), grade `Observation`s, `Task` + `Flag` for level ≥ 2
  (one open alert Task per patient, priority only rises), `Composition` for the doctor summary, chat `Communication`s
  with `inResponseTo`, and a `Provenance` (agent = navigator `Device` + version, entities = the inputs).

After a seed: dev 14 patients / 572 resources, extended 100 patients / 4 115 resources, plus 4 Questionnaires and 1
Device.

```bash
curl -u SuperUser:SYS "http://localhost:52773/fhir/r4/Patient?_summary=count"                       # 114
curl -u SuperUser:SYS "http://localhost:52773/fhir/r4/Observation?patient=ONC-001&category=laboratory&_summary=count"
curl -u SuperUser:SYS "http://localhost:52773/fhir/r4/RiskAssessment?subject=Patient/ONC-001"
curl -u SuperUser:SYS "http://localhost:52773/fhir/r4/Task?code=triage-alert&status:not=completed"
```

## 2. SQL over the same data

Created and loaded by `backend/app/fhir/sql_tables.py` (DDL in `iris/sql/meddi_tables.sql`), run by the seed.
`LEVEL` is reserved in IRIS SQL, so level columns are `TriageLevel`.

| Table / view | Content | Filled by |
|---|---|---|
| `MEDDI.Triage_Rule` | the 49 rules of `app/triage/rules.yaml` | `sql_tables.py` |
| `MEDDI.Drug_Class` | drug → risk class | `sql_tables.py` |
| `MEDDI.Eval_Expected` | ground-truth levels of all 1 320 check-ins | `sql_tables.py` |
| `MEDDI.Triage_Result` | every triage the API makes (level, step, contact, rule ids, confidence) | `writers.py::_save_triage_result` |
| `MEDDI.Eval_Run` | prepared for eval runs (not filled yet) | – |
| `MEDDI.FHIR_Observation`, `MEDDI.FHIR_Risk`, `MEDDI.FHIR_Task` | `JSON_TABLE` views over the FHIR resource table `HSFHIR_X0001_R.Rsrc` | `meddi_tables.sql` |

Demo queries (SQL explorer, namespace FHIRSERVER):

```sql
-- weight trend of ONC-007 (creeping heart failure on trastuzumab), straight from FHIR Observations
SELECT EffectiveAt, NumValue AS kg, Device FROM MEDDI.FHIR_Observation
WHERE PatientRef = 'Patient/ONC-007' AND Loinc = '29463-7' ORDER BY EffectiveAt;

-- the same without the view
SELECT j.measured, j.kg
FROM HSFHIR_X0001_R.Rsrc r, JSON_TABLE(r.ResourceString, '$' COLUMNS (
    patient VARCHAR(40) PATH '$.subject.reference', measured VARCHAR(40) PATH '$.effectiveDateTime',
    loinc VARCHAR(20) PATH '$.code.coding[0].code', kg NUMERIC(6,1) PATH '$.valueQuantity.value')) j
WHERE r.ResourceType = 'Observation' AND r.Deleted = 0 AND j.loinc = '29463-7' AND j.patient = 'Patient/ONC-007'
ORDER BY j.measured;

-- fevers ≥ 38 °C, levels, open alerts
SELECT PatientRef, EffectiveAt, NumValue AS celsius FROM MEDDI.FHIR_Observation WHERE Loinc = '8310-5' AND NumValue >= 38;
SELECT TriageLevel, COUNT(*) FROM MEDDI.FHIR_Risk GROUP BY TriageLevel;
SELECT PatientRef, Priority, OwnerName, SlaEnd FROM MEDDI.FHIR_Task WHERE Code = 'triage-alert' AND Status <> 'completed' ORDER BY SlaEnd;

-- which rule fired, joined to the rule table
SELECT t.CheckinId, t.TriageLevel, r.RuleId, r.Expr FROM MEDDI.Triage_Result t
JOIN MEDDI.Triage_Rule r ON t.RuleIds [ r.RuleId WHERE t.PatientId = 'ONC-004';
```

FHIR SQL Builder (the official projection tool) is available at `/csp/fhir-management` → FHIR SQL Builder (repository
`localhost:52773`, endpoint `/fhir/r4`, analysis → transform spec → projection). We did not script it; the views above
give the scripted SQL access. More queries: `docs/fhir-mapping.md`.

## 3. Vector Search

`backend/app/agent/vectors.py` (build: `python -m app.agent.vectors --build`, also run by `scripts/seed.sh`).

```sql
CREATE TABLE MEDDI.Guide_Chunk (Id INT, Source VARCHAR(200), "Section" VARCHAR(120), Lang VARCHAR(5),
    Audience VARCHAR(10), Txt VARCHAR(4000), Emb VECTOR(DOUBLE, 1536));
CREATE INDEX GuideHNSW ON TABLE MEDDI.Guide_Chunk (Emb) AS HNSW(Distance='Cosine');
CREATE TABLE MEDDI.Checkin_Text (CheckinId VARCHAR(20), PatientId VARCHAR(12), Scenario VARCHAR(12),
    Lang VARCHAR(5), Txt VARCHAR(4000), Emb VECTOR(DOUBLE, 1536));
CREATE INDEX CheckinHNSW ON TABLE MEDDI.Checkin_Text (Emb) AS HNSW(Distance='Cosine');
```

- `Guide_Chunk`: 119 rows: 76 clinician chunks (`pravidla_triaze.md`, README rules) and 43 patient chunks (questionnaire
  warnings, the cs/sk patient guide in `app/agent/patient_guide.py`). Embeddings `text-embedding-3-small` (1 536 dims),
  cached in `backend/cache/embeddings`.
- `Checkin_Text`: 95 dev check-in messages, for wording examples only (never for the level), excluding the current
  patient.
- Query (`search_guidance`, `search_similar_checkins`):
  `SELECT TOP 5 Source, "Section", Txt, VECTOR_COSINE(Emb, TO_VECTOR(?, DOUBLE)) AS Score FROM MEDDI.Guide_Chunk
  WHERE Audience = 'patient' AND Lang = ? ORDER BY Score DESC`.
- Used by the navigator chat (`app/agent/navigator.py`: the hits are the only allowed source of advice text and are
  cited) and by the MCP tools. `Section` is reserved in IRIS SQL, hence the quotes.

```bash
cd backend && PYTHONPATH=. .venv/Scripts/python.exe -m app.agent.vectors --search "mam hnacku" --lang sk
# 0.39 guide:pacient#prujem Pri hnačke pite často po malých dúškoch …
```

## 4. Interoperability production `MEDDI.Production`

Classes in `iris/src/MEDDI/`, installer `iris/scripts/install.sh`, full description in `docs/interop.md`.

| Flow | Hosts | Python side |
|---|---|---|
| Inbound HL7v2 labs → FHIR | `MEDDI.LabHL7.Service` (`EnsLib.HL7.Service.FileService`, `iris/inbox/*.hl7`, 2.5.1) → `MEDDI.LabHL7.Process` (`HS.Gateway.HL7.HL7ToSDA3.GetSDA`) → `MEDDI.SDA3ToFHIR` (`HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process` with `MEDDI.LabHL7.Transform`: Patient id = PID-3, lab identifiers as in the seed, conditional create) → `HS.FHIRServer.Interop.Operation` → `/fhir/r4` | `backend/app/interop/hl7.py` writes ORU^R01 messages (`--drop` all draws, `--new` the last draw as a new draw now) |
| Outbound alerts | `MEDDI.Alert.Service` (called over the native API) → `Ens.StringRequest` → `MEDDI.Alert.Operation` (`EnsLib.HTTP.OutboundAdapter`) → `POST http://host.docker.internal:8100/mock/meddi/requests` | `backend/app/interop/alerts.py::send_alert_via_iris`, called from `app/services/side_effects.py` for every task of level ≥ 2 (direct POST fallback when IRIS is down); mock in `app/api/mock_meddi.py` |

Demo:

```bash
cd backend
PYTHONPATH=. .venv/Scripts/python.exe -m app.interop.hl7 --patient ONC-001 --new   # 40 → 50 lab Observations on ONC-001
curl localhost:8100/mock/meddi/requests                                             # alerts delivered by MEDDI.Alert.Operation
```

Then open the message viewer: the HL7 file, the SDA3, the FHIR transaction and the alert POST are all traced.

## 5. Python native API and DB-API (`intersystems-irispython`)

- DB-API (`iris.connect(...)`, `cursor.execute`) for the SQL tables (`app/fhir/sql_tables.py`, `app/fhir/writers.py`),
  Vector Search (`app/agent/vectors.py`) and `app/fhir/client.py::sql_connection`.
- Native API `iris.createIRIS(connection).classMethodValue("MEDDI.Alert.Service", "Send", body)` in
  `app/interop/alerts.py` to hand an alert to the production.

## 6. MCP server (agentic AI)

`backend/app/agent/mcp_server.py` (FastMCP, streamable HTTP on http://127.0.0.1:8101/mcp) exposes the tools of
`backend/app/agent/tools.py`: `get_patient_context`, `get_recent_checkins`, `get_trend`, `search_guidance` (IRIS
Vector Search), `get_contact`, `ask_followup`, `escalate` (can only raise a level), `find_similar_checkins`. They are
read-only over the patient data, pseudonymised (no name or birth date), and every call is logged as one JSON line to
`backend/logs/mcp.log`. Inside the chat the LLM gets the same tools bound to the current patient.

```bash
cd backend && PYTHONPATH=. .venv/Scripts/python.exe -m app.agent.mcp_server
tail -f backend/logs/mcp.log
```

## Not used (and why)

- Embedded Python inside IRIS: embeddings and chunking run in the FastAPI process (same code, simpler to debug in 24 h).
- IntegratedML: no time for the experimental „escalation in 48 h“ model; it would never set a level anyway.
- Scripted FHIR SQL Builder projections: done by hand in the UI if needed (see §2).
