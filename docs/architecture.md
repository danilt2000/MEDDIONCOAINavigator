# Architecture and build contract

The product spec is [`docs/spec.md`](spec.md). This file fixes the module boundaries, the Python interfaces between
modules and the HTTP API, so that each part can be built in parallel.

## Layout

```text
backend/app/
  config.py            settings from the repo-root .env (OPENAI_API_KEY, IRIS, FHIR)        [foundation]
  models.py            MEDDI input models + all shared output contracts                    [foundation]
  adapters/meddi_json.py  load_patients(dataset), load_ground_truth(dataset), load_questionnaires()  [foundation]
  main.py              FastAPI app, registers every router in app/api                       [foundation]
  context/             context_builder(as_of), baselines, drug classes                      [engine]
  triage/              rules.yaml, engine.py, router.py, responder.py, validator.py         [engine]
  nlu/lexicon_cs_sk.py, nlu/__init__.py (analyze = lexicon ∪ LLM)                           [engine]
  nlu/llm_extractor.py, llm/ (polish, summary writer), cache in backend/cache/              [llm]
  summary/             facts.py, summarizer.py                                              [engine]
  eval/                replay.py, metrics.py, report.py, CLI                                [engine]
  fhir/                httpx client, MEDDI -> FHIR mappers, seed, output writers, SQL tables [fhir]
  agent/               vector store, MCP server, navigator agent, chat pipeline             [navigator]
  api/chat.py          chat endpoints                                                       [navigator]
  api/mock_meddi.py    mock MEDDI monitoring-centre endpoint                                [interop]
  api/{meta,patients,checkins,queue,stats,replay}.py, store.py, services/                   [api]
iris/                  Dockerfile (IRIS for Health 2026.2 + FHIR server /fhir/r4), src/*.cls  [foundation, interop]
packages/api/          TypeScript types + fetch/SSE client mirroring this contract          [foundation]
packages/ui/           Material 3 components, tokens, triage colours                        [foundation]
apps/patient-pwa/      patient + caregiver PWA (P1–P6)                                       [patient-ui]
apps/doctor-web/       clinician web (C1–C6)                                                 [doctor-ui]
```

Rules for parallel work: write only inside the area you own; do not commit; do not edit `models.py`, `config.py`,
`main.py`, `packages/*` or another area. If you need a change there, put it in your final report. Never read
`nazev_scenare`, `vychazi_ze_scenare` or ground truth outside `app/eval`.

## Runtime

| Thing | Where |
|---|---|
| Python | `backend/.venv/Scripts/python.exe`, run from `backend/` with `PYTHONPATH=.` |
| API | `uvicorn app.main:app --port 8100` (port 8000 is taken on the dev machine) |
| IRIS | container `meddi-iris`, `docker compose up -d` at the repo root; superserver `localhost:1972`, web `localhost:52773` |
| IRIS login | `SuperUser` / `SYS`, namespace `FHIRSERVER` |
| FHIR R4 base | `http://localhost:52773/fhir/r4` (Basic auth, `application/fhir+json`) |
| IRIS portal | `http://localhost:52773/csp/sys/UtilHome.csp` |
| Host folder in the container | `./iris` is mounted at `/home/irisowner/meddi` (HL7 file drop: `iris/inbox`) |
| LLM | OpenAI, `settings.llm_model` (`gpt-6-luna`), embeddings `text-embedding-3-small` (1536) |
| Patient PWA / clinician web | Vite on 5173 / 5174, `/api` proxied to 8100 |

IRIS Community Edition allows 8 connections: open at most 2 DB-API connections per process and close them.

## Python interfaces

```python
# app/context/builder.py                                            [engine]
def build_context(patient: Patient, as_of: datetime, extra_checkins: list[Checkin] = []) -> PatientContext
    # only data with timestamp <= as_of; exams only from earlier days; extra_checkins = live check-ins from the store

# app/nlu/__init__.py                                               [engine, calls llm]
def analyze(checkin: Checkin, ctx: PatientContext, use_llm: bool = True) -> NluResult
def analyze_text(text: str, ctx: PatientContext, author: str, use_llm: bool = True) -> NluResult   # chat messages

# app/nlu/llm_extractor.py                                          [llm]
def extract_llm(texts: list[tuple[str, str]], lang_hint: str, author: str) -> NluResult | None
    # texts = [(source, text)] with source in zprava|priloha|dotaznik|chat; disk cache keyed by input hash;
    # returns None when the LLM is off or fails; facts without a verbatim quote are dropped

# app/triage/engine.py                                              [engine]
def triage(checkin: Checkin, ctx: PatientContext, nlu: NluResult) -> TriageOutput
def triage_chat(patient_id: str, text: str, author: str, ctx: PatientContext, nlu: NluResult, at: datetime) -> TriageOutput

# app/triage/router.py                                              [engine]
def route(level: int, at: datetime, missed_checkins: bool = False) -> tuple[Step, str | None, bool, datetime | None]
    # (doporuceny_krok, doporuceny_kontakt, upozornit_tym, sla_do)

# app/triage/validator.py                                           [engine]
def validate_patient_text(text: str, level: int, lang: str, meds: list[Lek], contact: str | None) -> list[str]  # [] = ok

# app/llm/polish.py                                                 [llm]
def polish(template_text: str, lang: str, level: int, addressee: str) -> str | None   # caller validates

# app/summary/summarizer.py                                         [engine, LLM writer from llm]
def build_summary(patient: Patient, ctx: PatientContext, outputs: list[TriageOutput], reason: str) -> DoctorSummary

# app/llm/summary_writer.py                                         [llm]
def write_summary(facts: list[SummaryFact], header: str, lang: str = "cs") -> str | None   # caller checks numbers/dates

# app/eval/replay.py                                                [engine]
def replay(patients: list[Patient], use_llm: bool) -> Iterator[tuple[Checkin, PatientContext, TriageOutput]]
# app/eval/metrics.py                                               [engine]
def evaluate(outputs: list[TriageOutput], expected: dict[str, GroundTruth]) -> dict   # metrics, confusion, errors
# CLI: python -m app.eval --dataset dev|rozsirena|all [--no-llm]  -> backend/reports/eval_<dataset>.json + table

# app/fhir/*                                                        [fhir]
def seed(datasets: list[str]) -> None            # Questionnaires + per-patient transaction Bundle, no check-ins
def write_checkin(patient: Patient, checkin: Checkin, output: TriageOutput | None) -> None
def write_alert(task: QueueTask, output: TriageOutput) -> None          # Task + Flag
def write_summary(summary: DoctorSummary) -> None                      # Composition
def write_chat(patient_id: str, message: dict) -> None                 # Communication
def fhir_available() -> bool
    # every writer is a no-op returning quickly when IRIS is down; all writes tagged meta.tag synthetic + dataset

# app/agent/navigator.py                                            [navigator]
async def chat_turn(patient_id: str, text: str, author: str, lang: str | None) -> NavigatorReply
async def stream_chat_turn(patient_id: str, text: str, author: str, lang: str | None) -> AsyncIterator[dict]
    # events: {"event": "card", "data": LevelCard} | {"event": "delta", "data": str} | {"event": "done", "data": NavigatorReply}
# app/agent/mcp_server.py: FastMCP server with the §9 tools, `python -m app.agent.mcp_server` (streamable-http :8101)
```

Until a module lands, callers import it lazily and fall back (e.g. `try: from app.triage.engine import triage`).

## HTTP API (`/api`, JSON; frontends use `packages/api`)

| Method | Path | Response |
|---|---|---|
| GET | `/api/health` | `{iris, fhir, llm, mcp, version}` |
| GET | `/api/demo/state` | `{now, dataset}` simulated clock; `POST /api/demo/state {now, dataset}` sets it |
| GET | `/api/questionnaires` | the 4 MEDDI questionnaire definitions as in `dotazniky_definice.json` |
| GET | `/api/contacts` | `{monitoring_centre: {phone, hours}, on_duty: {phone}, ems: {phone}}` |
| GET | `/api/patients?dataset=dev` | `PatientListItem[]` |
| GET | `/api/patients/{id}` | `PatientDetail` |
| GET | `/api/patients/{id}/context?as_of=` | `PatientContext` |
| GET | `/api/patients/{id}/timeline?as_of=` | `TimelineItem[]` |
| GET | `/api/patients/{id}/trends?metric=&days=` | `{metric, unit, points: [{at, value, source}]}`; metrics `weight, bp_sys, bp_dia, pulse, temperature, glucose, stools, pain` |
| GET | `/api/patients/{id}/triage` | `TriageOutput[]` newest first |
| GET | `/api/patients/{id}/summary?as_of=&reason=` | `DoctorSummary` |
| POST | `/api/checkins` | body = check-in in the MEDDI JSON shape (`checkin_id`, `datum`, `cas` may be omitted: server fills them from the demo clock) → `TriageOutput` |
| GET | `/api/checkins/{id}/triage` | `TriageOutput` |
| GET | `/api/chat/{patient_id}/messages` | `ChatMessage[]` of the current conversation (after the last hide) |
| POST | `/api/chat/{patient_id}/hide` | starts a new conversation → `[]`; nothing is deleted, the timeline keeps every message |
| POST | `/api/chat/{patient_id}/messages` | `{text, author: "pacient"|"pecujici", lang?}` → `NavigatorReply` |
| POST | `/api/chat/{patient_id}/stream` | same body, SSE events `card`, `delta`, `done` |
| GET | `/api/queue?status=open` | `QueueItem[]` (QueueTask + patient name, age, regimen, cycle_day) sorted by level then SLA |
| POST | `/api/tasks/{id}/action` | `{action: "accept"|"call"|"telekonzultace"|"close", note?}` → `QueueItem` |
| GET | `/api/stats/kpi` | `{today_by_level, open_tasks, sla_breached, missed_checkins, median_minutes_to_accept}` |
| GET | `/api/stats/daily?from=&to=` | `[{date, by_level: {"1":n,"2":n,"3":n,"4":n}, checkins, missed}]` |
| GET | `/api/stats/symptoms?from=&to=` | `[{symptom, patients, alerts, reports}]` |
| GET | `/api/stats/day/{date}` | `QueueItem[]`-like rows for patients with level ≥ 2 that day |
| GET | `/api/stats/symptom/{symptom}` | `[{patient_id, name, regimen, risk_badges, max_grade, series: [{date, grade}]}]` |
| GET | `/api/stats/patient/{patient_id}/symptoms` | `[{symptom, max_grade, reports}]` |
| POST | `/api/replay` | `{dataset, patients?, speed, until?}` → `{run_id}` |
| GET | `/api/replay/{run_id}/events` | SSE: `{checkin_id, patient_id, at, output: TriageOutput, expected?: GroundTruth}` then `end` |
| GET | `/api/eval/{run_id}` | `EvalReport` `{metrics, confusion: number[4][4], errors[]}`; `run_id = latest-dev`/`latest-rozsirena` serve the last CLI report |
| POST | `/mock/meddi/requests` | mock MEDDI monitoring-centre inbox (receives alerts from the IRIS production) |
| GET | `/mock/meddi/requests` | what the mock received |

`PatientListItem` = `{patient_id, dataset, name, age, sex, lang, diagnosis, regimen, cycle, cycle_day, risk_badges[], filled_by, last_level, last_checkin_at, open_task}`.
`TimelineItem` = `{kind: "checkin"|"lab"|"team_event"|"exam"|"chat"|"missed", at, title, detail, level?, ref}`.
`ChatMessage` = `{id, at, role: "user"|"navigator", author, text, level_card?, followup_question?}`.
Risk badges: `IO`, `FP` (fluoropyrimidine), `irinotekan`, `antikoagulace`, `antiangiogenní`, `kardiotoxická`, `opioid`, `paliativní`, `nadir`.
