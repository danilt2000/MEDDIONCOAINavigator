# MEDDI ONCO — AI navigator: MVP spec

Oct 16, 2026 · @danil

## 1. Goal and context

Build a working MVP of an **AI navigator for MEDDI Onco patients between check-ups**. It reads every home check-in (MEDDI questionnaire, free text, measurements, photo note) in the context of the treatment, assigns one of **4 triage levels** with an explanation, gives the patient one clear next step, alerts the MOÚ monitoring centre for levels 2–4 and writes a **30-second summary** for the doctor. The patient or a caregiver can also **chat with the AI directly**.

- **Challenge:** Rakathon 2026, MEDDI ONCO „AI společník pacienta mezi kontrolami“. MEDDI Onco is the telemedicine platform used at Masarykův onkologický ústav (MOÚ) since 2020.
- **Prizes:** the MEDDI challenge (judging in §2) and the InterSystems challenge (1 500 EUR: innovation, real-world impact, use of InterSystems technology, technical coherence).
- **Platform:** InterSystems IRIS for Health is the backbone: FHIR R4 repository, SQL, Vector Search, Interoperability and an MCP server for the AI agent (§6).
- **Reused from the Hlídač spec:** stack, IRIS setup, FHIR conventions, adverse-event notation with source („Průjem G2 (pacient)“), Material 3 + PWA, the screen designs.
- **New for MEDDI:** 4-level triage with hard rules and working-hours routing, chronological replay with evaluation against ground truth, AI navigator chat, caregiver mode, Slovak and diacritics-free messages, contradictions, missed check-ins.
- **Hard limits:** only the synthetic data from the packages; the system never diagnoses and never changes treatment; levels 2–4 always end with a health professional.

**For the implementing agent:** this document is the complete brief. Build what it describes; unresolved points and their defaults are in §15.

## 2. What MEDDI asks for and how we answer it

Every requirement from the challenge deck and the data README maps to one component of the MVP; the jury scores 5 weighted criteria on a hidden set of 6 patients.

| Requirement (deck / README) | Our answer | § |
| --- | --- | --- |
| Regularly and clearly finds out the patient's state, symptoms, their intensity and trend | MEDDI questionnaires in exact wording + free text + vitals + photo note; follow-up questions in the chat; trends per symptom and measurement | 8, 9 |
| Works with treatment context, medicines and health data | Context snapshot: regimen, cycle and cycle day (nadir D7–14), drug risk classes, comorbidities, labs, team events — all FHIR in IRIS | 7, 8 |
| Integrated into MEDDI Onco via SDK or API | Adapter layer (JSON files now, MEDDI API later) + proposed webhook/REST contract; all outputs structured JSON and FHIR | 11 |
| Recognises risky changes and sorts them into severity levels | Deterministic engine: hard rules = minimum level, context modifiers, trend detectors; level = maximum | 8 |
| Recommends the patient a clear next step | Step and contact by level × working hours; plain-language reply in Czech or Slovak | 8 |
| Alerts the care team when things get risky | FHIR Task + Flag for levels 2–4 in the monitoring-centre queue, with SLA timers | 8, 10 |
| Short summary of the course for the doctor | 30-second summary in the structure of `vzorove_souhrny_pro_lekare.md`, every claim linked to a dated record | 8 |
| No diagnosis, no treatment change, human oversight, explainability, safe escalation | Enforced in code: output validator, „when in doubt, go up“, rule ids and quotes on every result | 8 |

| Jury criterion | Weight | What we show |
| --- | --- | --- |
| Clinical benefit and safety | 30 % | 0 under-triaged red on replay, hard rules never broken, escalation when unsure |
| Usability for patient and team | 25 % | one-question-per-screen check-in, chat, caregiver mode, queue with SLA, 30-second summary |
| Technology and AI quality | 20 % | IRIS FHIR + Vector Search + MCP agent, evaluation harness with metrics |
| UI simplicity | 15 % | Material 3, one primary action per screen, colour + icon + words for every level |
| Integration and development potential | 10 % | adapter, API contract, AWS EU deployment plan |

**How the jury evaluates** (hidden set, replayed in time): catching every red and orange situation — under-triaging red is the worst error; the number of unnecessary escalations; correct routing by working hours; clarity for the patient and explainability for the doctor; quality of the doctor summary.

**Deck tips we follow:** use the treatment context and the trend; the patient's message beats the questionnaire; a clear human next step without jargon; a doctor summary readable in 30 s; propose the integration (no API during Rakathon); bonus for voice (deck contact: Jiří Pecina).

## 3. Input data

Two synthetic JSON packages — the dev set (14 patients, 171 check-ins) and the extended set (100 variants, 1 149 check-ins) — both with a reference evaluation of every check-in. The jury tests on 6 hidden patients with the same structure, so tune on principles, not on these patients.

| Package | Contents | Use |
| --- | --- | --- |
| `rakathon_meddi_onco_data` (dev) | `README.md`, `docs/pravidla_triaze.md`, `docs/dotazniky_definice.json`, `docs/vzorove_souhrny_pro_lekare.md`, `docs/pacientska_cesta_meddi_onco.md`, `pacienti/ONC-xxx.json` ×14, `ground_truth/ONC-xxx.json` ×14 | rules, seed, main evaluation |
| `rakathon_meddi_onco_rozsirena_sada` (extended) | `README.md`, `pacienti/ONC-R001…R100.json`, `ground_truth/` ×100; field `vychazi_ze_scenare` | robustness: false alarms, wording variants (a third without diacritics), \~12 % missing days |
| Hidden set (jury) | 6 patients, same structure | final test |

**Levels:** dev 115 green · 37 yellow · 13 orange · 6 red; extended 752 · 262 · 92 · 43.

**Facts that drive the design (dev set):** 90 of 171 check-ins arrive outside monitoring-centre hours; 12 are filled in by a daughter; 3 are missing (`stav: nevyplneno`); 5 carry a photo note; one patient writes Slovak (ONC-018).

### Patient file `pacienti/ONC-xxx.json`

| Field | Content |
| --- | --- |
| `patient_id`, `synteticka_data`, `sada` | id; always `true`; `dev` or `rozsirena` |
| `nazev_scenare` | scenario label — orientation only, **the engine must never read it** |
| `obdobi_sledovani` | `od`, `do` |
| `demografie` | `jmeno_fiktivni`, `vek`, `pohlavi`, `jazyk` (`cs`/`sk`), `kraj`, `domacnost`, `digitalni_gramotnost`, `vyplnuje` |
| `diagnoza` | `diagnoza`, `mkn10`, `stadium`, `biomarkery`, `datum_diagnozy` |
| `ecog_vychozi`, `komorbidity`, `alergie`, `predem_vyslovena_prani`, `antropometrie` | baseline |
| `lecba` | `zamer`, `rezim`, `leky`, `delka_cyklu`, `cykly[{cyklus, den_sledovani, datum_d1}]`, `poznamka` |
| `leky[]` | `lek`, `davka`, `frekvence`, `indikace`, `typ` (`onkologicky` / `podpurny` / `chronicky` / `rezim`), `od_data`, `do_data`, `pri_potizich` |
| `laboratore[]` | `odber_id`, `datum`, `cas`, `kod`, `test`, `hodnota`, `jednotka`, `ref_min`, `ref_max`, `priznak` (`L`/`H`) |
| `vysetreni[]` | `datum`, `vysetreni`, `vysledek` (ECHO, CT, MR, hemocultures; date only) |
| `udalosti_tymu[]` | `datum`, `cas`, `typ`, `autor`, `text`; types `telekonzultace`, `zmena_lecby`, `kontakt_sestra`, `kontakt_psycholog`, `hospitalizace`, `propusteni`, `aplikace_lecby`, `pokus_o_kontakt`, `konzultace_rt`, `navsteva_hospic` |
| `checkiny[]` | home check-ins (next table) |

### Check-in `checkiny[]`

| Field | Content |
| --- | --- |
| `checkin_id`, `datum`, `cas`, `den_sledovani` | id and timestamp (day 1 = start of monitoring) |
| `cyklus`, `den_cyklu` | cycle and day in the cycle (D1 = application); `null` for continuous treatment |
| `stav`, `vyplnil` | `vyplneno` / `nevyplneno`; `pacient` or a relative (`dcera`) |
| `dotazniky[]` | `dotaznik_id`, `odpovedi[{otazka_id, otazka, odpoved, odpoved_index, barva, upozorneni}]`, `nejvyssi_barva`, `zobrazena_upozorneni` |
| `vitalni_funkce` | object of `{hodnota, zdroj}`: `teplota_c`, `tk_sys`, `tk_dia`, `tepova_frekvence`, `glykemie_mmol_l`, `vaha_kg`, `dechova_frekvence`; also accept `spo2` (used by the rules, absent in the data) |
| `zprava_pacienta` | free text: typos, no diacritics, Slovak; may contradict the questionnaire |
| `prilohy[]` | text description of a photo, e.g. „foto\_port.jpg – zarudnutí cca 4 cm v okolí portu, bez hnisu“ |

### Ground truth `ground_truth/ONC-xxx.json`

A list joined on `checkin_id`: `uroven` (1–4) · `doporuceny_krok` (`dalsi_sledovani` / `kontaktovat_tym` / `telekonzultace` / `neodkladna_pomoc`) · `upozornit_tym` · `doporuceny_kontakt` · `klicove_nalezy[]` · `varovne_priznaky[]` · `zduvodneni` · `doporuceni_pro_pacienta`. Our output uses the same field names (§8.10).

### Questionnaires `docs/dotazniky_definice.json`

| `dotaznik_id` | When | Items | Notes |
| --- | --- | --- | --- |
| `nezadouci_ucinky` — Nežádoucí účinky onkologické léčby | every check-in | 25, branching via `podminka` (e.g. `ucinky:1` → stool questions) | answers carry a colour (`zelena` / `zluta` / `cervena`) and sometimes a warning shown to the patient |
| `psychoonkologicky_screening` — Psychoonkologický screening MOÚ | start, \~day 14, when mood worsens | 3 scales 1–10 + 6 yes/no | no colours, no official scoring key |
| `bolest_analgeticka_terapie` — Bolest po nastavení analgetické terapie | pain titration (ONC-011, ONC-014) | NRS, satisfaction, SOS doses per day, side effects |  |
| `esas` — ESAS | weekly, palliative (ONC-014) | 10 scales 1–10 | colours simplified: 1–3 green, 4–5 yellow, 6–10 red |

Scale direction: „Jak se celkově cítíte?“ 1 = best, 5 = very bad; ESAS, pain and psycho scales: low = fewer problems, except „Zvládání situace“ (high = coping well). **The questionnaire colours judge each answer alone and see no treatment, trend, vitals or message — one input, never the result** (38,0–39,0 °C is yellow in the app but red during chemotherapy).

**Replay rule (mandatory):** process check-ins chronologically; at each check-in the system may see only what was known by then — earlier check-ins, labs, team events and exams. It must not know a later hospitalisation or result (details in §12).

## 4. Users and scope

The MVP serves the patient, the caregiver, the monitoring-centre nurse and the MOÚ doctor, plus a demo operator who replays the data for the jury.

| Role | Device | Main jobs |
| --- | --- | --- |
| Patient | phone (PWA) | check-in, see the result and the next step, chat with the navigator, call the right number |
| Caregiver (e.g. daughter) | phone | fills in for the patient; is addressed directly; their own strain is assessed |
| Monitoring-centre nurse (MOÚ, Mon–Fri 7:00–15:30) | desktop | queue by level and SLA, takes over, calls, assigns to a doctor, records the outcome |
| MOÚ doctor / on-duty doctor (724 590 848) | desktop, phone | reads the 30-second summary, decides, records the decision |
| Demo operator / jury | desktop | replay console, metrics |

**In scope (MVP)**

- Load the dev and extended packages into IRIS as FHIR R4.
- Triage engine (4 levels), routing by working hours, team alerts, doctor summary.
- Patient PWA: home, check-in, result, navigator chat, history.
- Clinician web: queue, monitoring dashboard with drill-downs, patient detail.
- Replay and evaluation harness against the ground truth.
- MEDDI integration proposal and AWS EU deployment plan (documented, not connected).

**Out of scope**

- Connecting to the real MEDDI API (not available during Rakathon).
- Real patient data, real authentication (a demo role switcher only), eRecept, video calls.
- Any diagnosis, dose advice or treatment change.
- Analysing real photos: the data has only text descriptions (vision is a COULD in §16).

## 5. Architecture

Same three layers as Hlídač: a React PWA, a FastAPI backend with the triage engine and the AI agent, and InterSystems IRIS for Health as the data and AI platform. The engine is deterministic; the LLM extracts facts from free text, polishes wording and runs the chat, but never sets the level.

```text
Patient PWA (/p) · Clinician web (/c) · Replay console (/demo)
        │  REST + SSE (JSON)
        ▼
FastAPI backend (Python 3.11)
├─ adapters: MeddiJsonAdapter (now) · MeddiApiAdapter (later)
├─ context_builder(as_of)
├─ nlu: LLM extractor + cs/sk lexicon safety net
├─ triage_engine: hard rules → context → trends → max
├─ router: level × working hours → step, contact, SLA
├─ responder: template + LLM polish + validator
├─ summarizer: 30-second doctor summary
├─ alerting: FHIR Task + Flag, outbound message to MEDDI
├─ navigator_agent: chat over MCP tools
└─ replay + eval harness
        │
        ├── FHIR REST · SQL · Vector ──► InterSystems IRIS for Health (Docker)
        │                                ├─ FHIR R4 repository
        │                                ├─ FHIR SQL Builder
        │                                ├─ Vector Search (RAG, similar check-ins)
        │                                ├─ Interoperability: HL7v2 labs in, alerts out
        │                                ├─ MCP server (tools for the agent)
        │                                └─ Embedded Python (load-time jobs)
        │
        └── LLM API ──► prototype: OpenAI · Azure OpenAI EU · Ollama
                        production: Amazon Bedrock in an EU region
```

**One check-in, end to end**

1. **Ingest.** The PWA or the replay posts a check-in in the MEDDI JSON shape. The adapter writes one FHIR transaction Bundle to IRIS: QuestionnaireResponse(s), vital-sign Observations, Communication (message), DocumentReference (photo note). A missing check-in becomes a Task `missed-checkin`.
2. **Context.** `context_builder(patient, as_of)` reads from IRIS only resources dated up to the check-in: Patient, Conditions, CarePlan (cycle, day in cycle), MedicationRequests with drug classes, labs, team events, the last 10 check-ins, baselines (weight, BP, pulse, usual stool count).
3. **Extract.** `nlu` turns free text (cs/sk, typos, no diacritics) and photo notes into typed facts with verbatim quotes (§8.7). A lexicon safety net runs in parallel; a red flag found by either counts.
4. **Triage.** `triage_engine` evaluates hard rules, context modifiers, trends, gaps and contradictions; level = maximum. Uncertainty keeps the higher level and adds a follow-up question.
5. **Route.** `router` maps level × check-in time to `doporuceny_krok`, `doporuceny_kontakt`, `upozornit_tym` and an SLA deadline.
6. **Reply.** `responder` fills the level template, lets the LLM polish it, then validates; on failure the plain template goes out.
7. **Alert.** Level ≥ 2 → FHIR Task (priority by level) + Flag in the monitoring-centre queue and an outbound message to the MEDDI mock; level ≥ 3 also gets a doctor summary (Composition).
8. **Store and show.** RiskAssessment + Provenance in IRIS; SSE push to the clinician web and the patient app.

**Repo layout**

```text
meddi-navigator/
  docker-compose.yml        # iris + api + web
  iris/                     # Dockerfile from the kit, production classes, SQL DDL, MCP config
  backend/app/
    adapters/               # meddi_json.py (prototype), meddi_api.py (stub)
    fhir/                   # httpx client, JSON -> FHIR mappers
    context/                # as_of snapshot, baselines, drug classes
    nlu/                    # llm_extractor.py, lexicon_cs_sk.py
    triage/                 # rules.yaml, engine.py, router.py, responder.py, validator.py
    summary/                # facts.py, summarizer.py
    agent/                  # navigator.py, mcp_tools.py, prompts/
    eval/                   # replay.py, metrics.py, report.py
  web/                      # React PWA: /p patient, /c clinician, /demo replay
  data/                     # unzipped packages, read-only
```

## 6. InterSystems IRIS — use as much as possible

IRIS is both the system of record and the AI platform: every check-in, triage result, alert and summary lives in IRIS as FHIR R4; Vector Search feeds the navigator and the explanations; Interoperability brings labs in and sends alerts out; an MCP server gives the AI agent safe tools over IRIS. This covers all three technologies the InterSystems challenge names: FHIR server, Vector Search and agentic AI.

**Setup (same as Hlídač):** IRIS for Health Community from the FHIR-AI-Hackathon-Kit (`Dockerfhir`). Portal `http://localhost:32783/csp/sys/UtilHome.csp`, login `_SYSTEM` / `ISCDEMO`, FHIR base `http://localhost:32783/csp/healthshare/demo/fhir/r4`. Community Edition allows about 8 concurrent connections: use one shared httpx client and an IRIS DB-API pool of at most 4.

| IRIS feature | What we use it for | Priority |
| --- | --- | --- |
| FHIR R4 repository | all patient data, check-ins and our outputs (§7); MEDDI could read them back over FHIR | MUST |
| FHIR SQL Builder | SQL projections of Observation, QuestionnaireResponse items, RiskAssessment and Task for trends, the dashboard and metrics | MUST |
| Vector Search | `Guide_Chunk`: rules, questionnaire warnings, approved patient texts → RAG for the chat and the explanations; `Checkin_Text`: similar past check-ins as wording examples | MUST |
| MCP server over IRIS | tools for the navigator agent (§9): context, trends, guidance search, contacts, follow-up, escalation | MUST |
| Interoperability production | inbound `MEDDI.LabHL7.Service` (HL7v2 ORU^R01, file or TCP) → SDA → FHIR repository; outbound `MEDDI.Alert.Operation` → POST to a mock MEDDI monitoring-centre endpoint for every Task of level ≥ 2 | MUST (one inbound + one outbound flow) |
| Embedded Python | load-time jobs inside IRIS: chunking and embeddings for Vector Search, diacritics normalisation of message text | SHOULD |
| FHIR Provenance | a Provenance for every AI output (agent = navigator version, entities = inputs) | SHOULD |
| IntegratedML | experimental „risk of escalation within 48 h“ trained on the extended set; shown as a hint, never used for the level | COULD |

**HL7 → FHIR path (reused from Hlídač):** `HS.Gateway.HL7.HL7ToSDA3.GetSDA()` (expects HL7 2.5.1) → SDA3 → `HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process` → FHIR repository. Sample message in §12. Class names starting with `MEDDI.` are ours to create.

**Vector Search tables**

```sql
CREATE TABLE Guide_Chunk (Id INT, Source VARCHAR(200), Section VARCHAR(120), Lang VARCHAR(5), Audience VARCHAR(10), Txt VARCHAR(4000), Emb VECTOR(DOUBLE, 1536));
CREATE INDEX GuideHNSW ON TABLE Guide_Chunk (Emb) AS HNSW(Distance='Cosine');
CREATE TABLE Checkin_Text (CheckinId VARCHAR(20), PatientId VARCHAR(12), Scenario VARCHAR(12), Lang VARCHAR(5), Txt VARCHAR(4000), Emb VECTOR(DOUBLE, 1536));

-- top 5 patient-facing passages for a chat question (embedding passed as a string)
SELECT TOP 5 Source, Section, Txt
FROM Guide_Chunk
WHERE Audience = 'patient' AND Lang = ?
ORDER BY VECTOR_COSINE(Emb, TO_VECTOR(?, DOUBLE)) DESC;
```

`Audience` is `patient` (approved patient-facing texts) or `clinician` (rules, rationale); the chat retrieves only `patient` chunks. `Checkin_Text` is used for wording examples only, never for the level; during evaluation it excludes the replayed patient and every variant of its scenario (`Scenario` = `vychazi_ze_scenare` or the dev id) to avoid leakage.

**MCP server:** built on the kit's V2 tutorial 5.2 (MCP server) with the agent pattern from 5.1 (agents and tools); the tool list is in §9.

## 7. Data model: MEDDI JSON → FHIR R4 in IRIS

Every MEDDI object becomes a standard FHIR R4 resource, and so does every output of ours (level, alert, summary, chat), so MEDDI could consume them over FHIR without new formats. All resources carry `meta.tag` `synthetic` + `dev` or `rozsirena`; identifiers use the system `urn:meddi:<type>` with the MEDDI ids.

| MEDDI JSON | FHIR R4 | Mapping notes |
| --- | --- | --- |
| `demografie` | Patient | identifier `ONC-001`; name from `jmeno_fiktivni`; gender; birthDate ≈ start of monitoring − age (flagged approximate); `communication.language` cs/sk; extensions: household, digital literacy, who fills in |
| `vyplnil: dcera` | RelatedPerson | relationship daughter; author of QuestionnaireResponse and Communication |
| `diagnoza` | Condition | ICD-10 from `mkn10`; stage in `stage.summary.text`; biomarkers in `note`; `onsetDateTime` = `datum_diagnozy` |
| `komorbidity[]`, `alergie[]` | Condition (problem list), AllergyIntolerance | text |
| `predem_vyslovena_prani` | Consent (advance directive) | shown to the team; never a reason to withhold help |
| `antropometrie`, `ecog_vychozi` | Observation 8302-2 height, 29463-7 weight, 39156-5 BMI, 89247-1 ECOG | baselines |
| `lecba` + `cykly[]` | CarePlan + one activity per cycle (scheduled D1) | `zamer`, `rezim`, `delka_cyklu`, `poznamka` |
| `leky[]` | MedicationRequest | `typ` → category; `pri_potizich` → `asNeededBoolean`; `davka` + `frekvence` → `dosageInstruction.text`; drug-class tags (§8.4) |
| `laboratore[]` | Observation (laboratory) | LOINC from `kod` (below), referenceRange, interpretation L/H |
| `vysetreni[]` | DiagnosticReport | `conclusion` = `vysledek` |
| `udalosti_tymu[]` | Encounter (`hospitalizace`, `propusteni`); Communication for the other types, `category` = `typ` | timestamp from `datum` + `cas` |
| questionnaire definitions | Questionnaire ×4 | `podminka` → `enableWhen`; colour and warning text → answerOption extensions |
| check-in `dotazniky[]` | QuestionnaireResponse | `authored` = check-in time; author Patient or RelatedPerson; `barva`, `upozorneni` kept in extensions |
| `vitalni_funkce` | Observation (vital-signs) | 8310-5 temperature; 85354-9 BP panel (8480-6 / 8462-4); 8867-4 pulse; 9279-1 respiratory rate; 59408-5 SpO2; 29463-7 weight; 14743-9 glucose (glucometer); `zdroj` → `device.display` |
| `zprava_pacienta` | Communication | sender Patient or RelatedPerson, language, `payload.contentString` |
| `prilohy[]` | DocumentReference | `description` = the text note |
| `stav: nevyplneno` | Task, code `missed-checkin` | drives the gap rule |
| triage result (ours) | RiskAssessment | `prediction.qualitativeRisk` = level 1–4; `basis` → evidence resources; `note` = rationale; `method` = engine version |
| symptom grade (ours) | Observation (survey) | display with source: „Průjem G2 (pacient)“, „Neutropenie G3 (odběr)“, „Mukozitida G3 (odhad systému)“ |
| alert (ours) | Task + Flag | Task.priority: level 2 `routine`, 3 `urgent`, 4 `stat`; owner = monitoring centre or on-duty doctor; `restriction.period.end` = SLA |
| patient reply, chat (ours) | Communication | sender Device „MEDDI navigátor“; thread via `inResponseTo` |
| doctor summary (ours) | Composition | sections Proč teď / K rozhodnutí, Léčba, Vývoj, Laboratoř, Nehlásí, K posouzení |
| every AI output | Provenance | agent = navigator + model version; entity = inputs |

**Lab `kod` → LOINC:** `leu` 6690-2 · `neu` 751-8 · `hb` 718-7 · `plt` 777-3 · `kreat` 14682-9 · `na` 2951-2 · `k` 2823-3 · `alt` 1742-6 · `bili` 14631-6 · `crp` 1988-5 · `tsh` 3016-3 · `ft4` 14920-3 · `mg` 2601-3 · `inr` 6301-6 · `alb` 1751-7 · `psa` 2857-1 · `testo` 14913-8 · `glu` 14749-6 · `moc_bilk` 20454-5 · `ntprobnp` 33762-6. Units stay as in the data (SI: µmol/l, mmol/l, 10^9/l).

**Engine tables (IRIS SQL, outside FHIR)**

```sql
CREATE TABLE Triage_Rule (RuleId VARCHAR(30), MinLevel INT, Area VARCHAR(40), Expr VARCHAR(500), PatientHint VARCHAR(300), Source VARCHAR(120), Active BIT);
CREATE TABLE Drug_Class (Drug VARCHAR(80), Class VARCHAR(40));
CREATE TABLE Triage_Result (CheckinId VARCHAR(20), PatientId VARCHAR(12), AsOf TIMESTAMP, Level INT, Step VARCHAR(20), Contact VARCHAR(160), NotifyTeam BIT, RuleIds VARCHAR(300), Confidence VARCHAR(10), EngineVersion VARCHAR(20));
CREATE TABLE Eval_Expected (CheckinId VARCHAR(20), Dataset VARCHAR(12), Level INT, Step VARCHAR(20), NotifyTeam BIT, Contact VARCHAR(160));
CREATE TABLE Eval_Run (RunId VARCHAR(20), CheckinId VARCHAR(20), Expected INT, Predicted INT, StepOk BIT, ContactOk BIT, NotifyOk BIT);
```

`rules.yaml` is the source of truth for the rules; `Triage_Rule` is its projection so the UI can show which rule fired. `Eval_Expected` is loaded from `ground_truth/` and is readable only by the eval module — never by the engine, the LLM or the MCP tools.

## 8. Triage logic: monitoring, risky changes, next step, alerts

The level is computed in code as the **maximum** of hard-rule minimums, context-adjusted symptom grades, trend detectors, the data-gap rule and the contradiction rule. The LLM only supplies extracted facts and wording. Uncertainty always resolves upward, with a follow-up question.

### 8.1 Levels and steps

| Level | UI | `doporuceny_krok` | `upozornit_tym` | Typical |
| --- | --- | --- | --- | --- |
| 1 | Zelená | `dalsi_sledovani` | false | expected mild (grade 1) problems, stable state; advice + when to call earlier |
| 2 | Žlutá | `kontaktovat_tym` | true | grade 2 without warning signs, worsening trend, non-adherence, psychological strain, missing data |
| 3 | Oranžová | `telekonzultace` | true, high priority | grade 3; grade 2 on risky treatment; threatening dehydration; suspected serious toxicity without immediate danger |
| 4 | Červená | `neodkladna_pomoc` | true, immediate | life-threatening state |

### 8.2 Routing by working hours

The monitoring centre works Monday–Friday from **07:00 (inclusive) to 15:30 (exclusive)**, Europe/Prague — verified on the boundary cases in the data. The ground truth ignores public holidays (28. 9. 2026 is handled as a working day), so evaluation runs without a holiday calendar; production switches the MOÚ calendar on by config. Output exactly these `doporuceny_kontakt` strings:

| Level | In working hours | Outside (evenings, nights, weekends) | SLA |
| --- | --- | --- | --- |
| 1 | `null` (the team sees it in the overview) | `null` | — |
| 2 | „monitorovací centrum – vyřízení do konce následujícího pracovního dne“ | „monitorovací centrum – následující pracovní den“ + when to call earlier | end of the next working day |
| 2, missed check-ins | „monitorovací centrum – vyřízení do konce následujícího pracovního dne“ | the same string (GT ONC-017-C08) | end of the next working day |
| 3 | „telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h“ | „sloužící lékař MOÚ 724 590 848 – ihned“ (no example in the data, §15) | 2 h / immediately |
| 4 | „155 / urgentní příjem“ | „155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)“ | team alerted within 15 min |

The eval harness compares the contact by category (`none`, `mc_next_day`, `tele_2h`, `on_duty`, `ems`) and reports exact-string matches separately.

### 8.3 Hard rules — minimum level, never lower

Taken from `pravidla_triaze.md` §3. Each rule has an id in `rules.yaml`, the signals that trigger it, and unit tests (positive, boundary, negative). The ground truth never breaks a hard rule, and neither may we.

**Red — level 4**

| Id | Rule | Signals |
| --- | --- | --- |
| R-FEVER | T ≥ 38.0 °C or chills during chemotherapy or within 6 weeks after it | `teplota_c`; `teplota` answer 1–4; text „zimnice“, „třesavka“, „triaška“ |
| R-HYPERPYREXIA | T ≥ 40 °C with any treatment, also outside the chemotherapy window (safety addition to §15) | `teplota_c`; `teplota` answer 3–4; a temperature ≥ 40 in the text |
| R-BREATH | dyspnoea at rest; SpO2 < 90 %; sudden dyspnoea with chest pain or palpitations | `dusnost` = 3; `spo2`; text |
| R-CHEST | new chest pain | `bol_hrud` = 1; text |
| R-NEURO | confusion, impaired consciousness or arousal, seizure, new limb weakness, speech disorder | text, caregiver reports |
| R-BLEED | blood in stool or vomit, black stool, blood in urine, nosebleed > 20 min, head injury on anticoagulation | `krvaceni_popis`, `moceni`, text, photo note |
| R-DIARRHEA | ≥ 7 stools above normal in 24 h, or diarrhoea with blood | `prujem` = 2–3; stool count in text |
| R-VOMIT | > 5 episodes in 24 h, or cannot keep fluids with signs of dehydration | `zvraceni` = 2–3; text |
| R-DEHYD | no urine > 10 h, fainting, systolic BP < 90 mmHg | `tk_sys`; text |
| R-ILEUS | no stool and no gas with vomiting or colicky pain | `zacpa` = 3 + vomiting or pain; text |
| R-BP | BP ≥ 180/110, or high BP with severe headache, visual or speech disturbance, chest pain | `tk_sys` / `tk_dia`; `bol_hlava` = 2; text |
| R-DKA | vomiting + abdominal pain + fast breathing in a diabetic or a patient on immunotherapy | answers + `dechova_frekvence` + comorbidity or drug class |
| R-OPIOID | new marked sleepiness, unresponsiveness or slowed breathing on opioids | text (often the caregiver), ESAS `ospalost`, `dechova_frekvence` ≤ 10 |
| R-SUICIDE | suicidal thoughts with a plan, intent or means | text (LLM + lexicon) |

Chemo window for R-FEVER = a cytotoxic drug (§8.4) given in the last 42 days, from `lecba.cykly[].datum_d1`, the active period of oral cytotoxics in `leky`, or a stated end of treatment (month only, e.g. „ukončena 08/2026“ → last day of that month).

**Orange — at least level 3**

| Id | Rule | Signals |
| --- | --- | --- |
| O-GENERAL | „Jak se celkově cítíte?“ = 5 | `pocit` index 4 |
| O-BREATH | SpO2 < 92 % or a drop of ≥ 3 points from the patient's usual value; new orthopnoea | `spo2`; text „spí na dvou polštářích“, „vsedě“ |
| O-DIARRHEA-RISK | 4–6 stools above normal on immunotherapy, fluoropyrimidines (5-FU, capecitabine) or irinotecan; any diarrhoea not responding to loperamide per schedule | `prujem` = 1 or count in text + drug class; text „i přes loperamid“ |
| O-IO-DIARRHEA-PAIN | any diarrhoea with abdominal pain on immunotherapy | `prujem` + `bol_bricho` + class |
| O-INTAKE | cannot keep fluids; newly liquids only with uncontrolled pain; little urine or dizziness on standing with low intake | `nevolnost` = 2–3, `afty` = 2–3, `nechutenstvi` = 3; text |
| O-VOMIT | 3–5 episodes in 24 h and cannot keep fluids | `zvraceni` = 1 + intake signal |
| O-BP-ANTIANGIO | BP ≥ 160/100 on antiangiogenic therapy | vitals + class |
| O-BLEED-ANTICOAG | any bleeding or new bruises on anticoagulation | `krvaceni` = 1; photo note „hematomy“; class |
| O-DVT | one-sided calf swelling and pain — always with pulmonary-embolism warning signs | text |
| O-PAIN | NRS ≥ 7 not relieved by a rescue (SOS) dose | pain questionnaire `nrs`, `sos`; text |
| O-BRAIN | morning headache with vomiting in a brain tumour | diagnosis + answers |
| O-IO-ENDO | strong thirst, frequent urination and weight loss on immunotherapy | text + weight trend |
| O-HYPO | glucose < 4 mmol/l on insulin | `glykemie_mmol_l` + class |
| O-PSYCH | „Ano“ to „napadá mě, že bych si nejraději vzal/a život“; statements of hopelessness („nemá to cenu“) | psycho screening `sebevrazda`; text |
| O-REPEAT | worsening although an examination is already scheduled — do not wait for the date | trend + team event |

### 8.4 Context modifiers and typical yellow situations

Seed `Drug_Class` from the dev data; match drug names in `leky`, `lecba.leky` and `lecba.rezim`, expanding regimen acronyms (AC = doxorubicin + cyclophosphamide; R-CHOP = rituximab, cyclophosphamide, doxorubicin, vincristine, prednisone; mFOLFOX6 = 5-FU, leucovorin, oxaliplatin; FOLFIRI = 5-FU, leucovorin, irinotecan).

| Class | Drugs in the data | Effect |
| --- | --- | --- |
| `cytotoxic` | doxorubicin, cyclophosphamide, oxaliplatin, 5-FU, irinotecan, carboplatin, etoposide, cisplatin, capecitabine, vincristine, paclitaxel | R-FEVER window; nadir D7–14 — never underestimate fever, teach temperature checks |
| `immunotherapy` | ipilimumab, nivolumab, atezolizumab | toxicity can start any time and progress fast: new diarrhoea, cough, dyspnoea, thirst or fatigue → always at least 2 |
| `fluoropyrimidine`, `irinotecan` | 5-FU, capecitabine; irinotecan | grade 2 diarrhoea → doctor the same day (3); on irinotecan loperamide continues until 12 h without diarrhoea, until then at least 2 |
| `anticoagulant` | warfarin (capecitabine raises INR) | bleeding judged more strictly (O-BLEED-ANTICOAG) |
| `antiangiogenic` | sunitinib, bevacizumab | hypertension, bleeding, perforation; in the sunitinib 4/2 pause BP falls and BP drugs can cause hypotension |
| `cardiotoxic` | anthracyclines, trastuzumab | oedema grade 2 or weight gain > 2 kg in 3 days → 2 |
| `platinum` | cisplatin, carboplatin | new tinnitus on cisplatin → 2 before the next dose |
| `neurotoxic` | oxaliplatin, vincristine, paclitaxel | neuropathy persisting between cycles or limiting fine motor skills → 2 before the next application |
| `corticosteroid` | dexamethasone, prednisone | glucose > 15 mmol/l with thirst or polyuria → 2 the same day |
| `opioid` | morphine retard, Oramorph, morphine syrup | R-OPIOID; ≥ 3 rescue doses a day → 2 |
| `insulin`, `metformin` | insulin lispro; metformin | O-HYPO; diarrhoea or dehydration on metformin → kidney risk noted for the doctor |

**Typical yellow (level 2)** — from `pravidla_triaze.md` §4, one rule each:

| Id | Situation |
| --- | --- |
| Y-GRADE2 | grade 2 symptom without warning signs: nausea with lower intake, constipation ≥ 3 days, mouth sores limiting eating, paronychia, hand–foot syndrome limiting activities |
| Y-IO-DIARRHEA | diarrhoea up to 3 stools above normal on immunotherapy (level 1 on other treatment) |
| Y-VOMIT | 3–5 vomiting episodes while the patient still drinks |
| Y-BP | BP ≥ 140/90 in at least 3 readings, or hypotension with dizziness on standing |
| Y-GLUCOSE | glucose > 15 mmol/l with thirst and frequent urination — team the same day |
| Y-NEURO | neuropathy persisting between cycles or limiting fine motor skills; new tinnitus on cisplatin — before the next dose |
| Y-CARDIO | oedema grade 2 or weight gain > 2 kg in 3 days on cardiotoxic therapy |
| Y-NUTRITION | weight loss ≥ 5 % in a month, self-care down by two steps, gradually falling intake |
| Y-PAIN | pain NRS 4–6, or ≥ 3 rescue doses a day |
| Y-PSYCH | moderate sadness or anxiety (default: `uzkost` or `depresivita` ≥ 6, or `zvladani` ≤ 3); first request for a psychologist without psychological care yet |
| Y-CAREGIVER | caregiver exhaustion |
| Y-ADHERENCE | skipping medicines (e.g. letrozole) |
| Y-GAP | 3 missed check-ins in a row in a stable patient; 1–2 missed → reminder only (level 1) |

**Other context:** chronic diseases (COPD, diabetes, heart failure, kidney disease) → judge the change against the patient's usual values, not absolute numbers. Old age, living alone, low digital literacy → lower threshold and a phone check. Palliative care and advance directives → information for the team, never a reason not to recommend help (24 h palliative line or hospice; if unreachable, 155).

### 8.5 Trends

Several worsening check-ins in a row can mean a higher level even when each looks harmless (`pravidla_triaze.md` §6.1). Baselines come from the first week of monitoring or `antropometrie`.

| Detector | Window | Rule |
| --- | --- | --- |
| T-WEIGHT-GAIN | 3 days | > 2 kg on cardiotoxic therapy → 2 |
| T-WEIGHT-LOSS | 30 days | ≥ 5 % below baseline → 2 |
| T-OEDEMA | consecutive check-ins | oedema spreading (evenings → also mornings) on cardiotoxic therapy → 2 |
| T-BP | last 3 readings | ≥ 140/90 in all 3 → 2; ≥ 160/100 on antiangiogenic → 3 |
| T-SPO2 | patient's usual value | drop of ≥ 3 points → 3 |
| T-SELFCARE | baseline ECOG or first `sobestacnost` | two steps worse → 2 |
| T-INTAKE | last 3 check-ins | intake answers getting worse → 2 |
| T-REPEAT | since the last team event | worse again after a telekonzultace or with an exam already booked → 3 (O-REPEAT) |

Trend findings always go into `klicove_nalezy` and into the doctor summary as a dated series („3 → 4 → 8 stolic nad normál“).

### 8.6 Special situations

- **The message beats the questionnaire.** When extracted facts are worse than the answers, use the worse variant, record the contradiction in `klicove_nalezy` and ask a follow-up in the patient's language. Example ONC-018-C03: the form shows no diarrhoea, the text says „od vcera mam hnacku asi 6 krat“ on irinotecan → 3 and „Píšete, že máte hnačku asi 6× za deň – je to tak?“. The level stays at the worse variant until answered.
- **The team is already acting.** After a team event (telekonzultace, hospitalisation) an improving state is judged on current data; a new or worse symptom is judged from scratch. Example ONC-018-C04 „Lepsie, 3 krat“ → 2 (irinotecan: loperamide until 12 h without diarrhoea).
- **Caregiver.** When `vyplnil` ≠ `pacient`, address the caregiver, assess their strain (exhaustion → 2) and treat their reports („mamka sténá“, „nejde probudit“) as facts about the patient.
- **Missing check-ins.** 1st and 2nd missed → reminder (level 1); 3rd in a row → 2 „kontaktovat pacienta“. High-risk patients escalate earlier (default: 2 missed during nadir D7–14 or on immunotherapy; §15).
- **Pre-agreed instructions only.** The reply may quote an instruction the patient already has, verbatim from `leky` (ONC-018 loperamide: „4 mg pri prvej riedkej stolici, potom 2 mg každé 2 h až 12 h bez hnačky“), or a standard safety line („Paralen neužívejte, dokud vás nevyšetří lékař“). It never computes or changes a dose.
- **Palliative care.** The advance directive is shown to the team; the reply still recommends help: the 24 h palliative team or hospice line, and 155 if unreachable. ONC-014-C09 (sleepiness, 8 breaths/min after an opioid increase) is red despite the directive.

### 8.7 Free-text extraction (NLU)

An LLM call with JSON-schema output and temperature 0 reads the message, the photo note and the free-text answers (`jine`, `krvaceni_popis`), pseudonymised. In parallel a deterministic lexicon (diacritics-insensitive regex for cs and sk: „hnačka / průjem / prujem“, „krv / krev“, „horúčka / teplota / 38,5“, „zimnice / třesavka“, „dýchat / dušnost“, „polštář“, „nemočí“…) catches red flags. Results are united, not intersected: a red flag found by either counts.

```json
{
  "lang": "sk",
  "author": "pacient",
  "facts": [
    {"type": "stool_count_above_normal", "value": 6, "period_h": 24, "certainty": "approx", "quote": "od vcera mam hnacku asi 6 krat"},
    {"type": "weakness", "value": true, "quote": "slaby som"}
  ],
  "negations": [],
  "patient_questions": [],
  "caregiver_strain": false
}
```

Fact types (closed list): `temperature_c`, `chills`, `stool_count_above_normal`, `blood_in_stool`, `black_stool`, `vomiting_episodes_24h`, `cannot_keep_fluids`, `no_urine_hours`, `fainting`, `dizziness_standing`, `dyspnea_rest`, `dyspnea_exertion`, `orthopnea`, `chest_pain_new`, `palpitations`, `confusion`, `drowsiness_new`, `breathing_slow`, `seizure`, `limb_weakness_new`, `speech_problem`, `bleeding_site`, `nosebleed_minutes`, `head_injury`, `bruises_new`, `abdominal_pain_nrs`, `colicky_pain`, `no_stool_no_gas`, `headache_severe`, `vision_problem`, `thirst_polyuria`, `weight_change_kg`, `edema`, `calf_swelling_one_side`, `pain_nrs`, `rescue_doses_per_day`, `liquids_only`, `weakness`, `suicidal_thoughts`, `suicide_plan_intent_means`, `hopelessness`, `missed_medication`, `caregiver_strain`, `port_redness`, `nail_fold_inflammation`, `skin_blisters`, `tinnitus`, `neuropathy_function_loss`, `cough_new`, `other`. Every fact must carry a verbatim `quote`; facts without one are dropped.

### 8.8 Questionnaire answer → signal

The engine reads `odpoved_index`; colours are kept only as evidence.

| `otazka_id` | Index → signal (grade estimate) |
| --- | --- |
| `pocit` | 4 („5 = velmi špatně“) → O-GENERAL |
| `sobestacnost` | 0–4 ≈ ECOG 0–4 → T-SELFCARE |
| `nechutenstvi` | 2 losing weight → G2 (2); 3 minimal intake, not manageable → O-INTAKE |
| `nevolnost` | 1 → G1; 2–3 intake at minimum → G3 → O-INTAKE |
| `zvraceni` | 0 = 1–2 a day G1; 1 = 3–5 G2 (Y-VOMIT if drinking, O-VOMIT if not); 2–3 → R-VOMIT |
| `prujem` | 0 = up to 3 above normal G1 (1; 2 on immunotherapy); 1 = 4–6 G2 (2; O-DIARRHEA-RISK on IO, fluoropyrimidine, irinotecan); 2–3 → R-DIARRHEA |
| `zacpa` | 1–2 → G2 (2 when ≥ 3 days); 3 → at least 3; with vomiting or colic → R-ILEUS |
| `afty` | 1 → G2 (2); 2 liquids only → 2, with uncontrolled pain O-INTAKE; 3 → O-INTAKE |
| `bol_hlava` | 2 → 2; with BP ≥ 180/110 or visual or speech symptoms → R-BP |
| `bol_hrud` | 1 new chest pain → R-CHEST |
| `bol_bricho` | 1–2 → 2; with any diarrhoea on immunotherapy → O-IO-DIARRHEA-PAIN |
| `bol_klouby` | 2 → 2 (watch adherence on aromatase inhibitors) |
| `brneni` | 1–2 → Y-NEURO before the next dose |
| `teplota` | 0 = 37.0–37.9; 1 = 38.0–39.0 → R-FEVER in the chemo window, otherwise 2; 2 (39–40) → R-FEVER in the window, otherwise 3; 3–4 (> 40) → R-FEVER in the window, otherwise R-HYPERPYREXIA (4) |
| `kuze` | 1 → G2 (2); 2 → G3 (3) |
| `unava` | 2 → 2 (fatigue alone never above 2) |
| `krvaceni` | 1 → at least 2; on anticoagulant → O-BLEED-ANTICOAG; the site in `krvaceni_popis` may hit R-BLEED |
| `moceni` | 1 → 2; blood in urine → R-BLEED |
| `dusnost` | 1 → G1; 2 → G2 (2; 3 if new on immunotherapy); 3 at rest → R-BREATH |
| psycho `sebevrazda` | Ano → O-PSYCH; plan, intent or means in text → R-SUICIDE |
| pain `nrs` + `sos` | NRS 4–6 or ≥ 3 SOS doses a day → 2; NRS ≥ 7 after an SOS dose → O-PAIN |
| ESAS | items ≥ 6 → findings for the palliative team; `ospalost` rising after an opioid increase → check R-OPIOID |

### 8.9 Patient reply and guardrails

The reply is a level template, polished by the LLM (at most 4 short sentences, no jargon), then checked by a validator. If the validator fails, the plain template goes out and the failure is logged.

| Level | Template (cs; sk variant for `jazyk: sk`) |
| --- | --- |
| 1 | „Děkujeme, dnešní záznam je v očekávaném rozmezí. Pokračujte podle doporučení. Ozvěte se dřív, pokud: {kdy\_dřív}.“ |
| 2 | „Váš záznam jsme předali týmu monitorovacího centra, ozve se vám {kdy}. Pokud se objeví {varovné\_příznaky}, volejte {kontakt}.“ |
| 3 | „Vaše potíže je potřeba ještě dnes probrat s lékařem. {Kdo} vám zavolá {kdy}. Do té doby {předem\_dohodnutý\_postup}. Při {varovné\_příznaky} volejte 155.“ |
| 4 | „Volejte ihned {kontakt\_4}. Nečekejte do rána. {bezpečnostní\_věta}“ |

**Validator (all must pass)**

- Levels 2–4 name the contact and the time („do konce zítřka“, „do 2 hodin“, „ihned“); level 4 starts with the call to action.
- No diagnosis words for the patient (blocklist incl. febrilní neutropenie, sepse, kolitida, srdeční selhání, trombóza, embolie, ketoacidóza, infarkt, metastáza). The doctor rationale may say „podezření na…“.
- No dose numbers unless copied verbatim from the patient's `leky`; no new medicines; no „nemusíte se bát“-type reassurance at level ≥ 2.
- The patient's language; the caregiver is addressed when they wrote.

### 8.10 Output per check-in

The first ten fields equal the ground-truth fields (string-compatible); the rest are ours.

```json
{
  "checkin_id": "ONC-018-C03",
  "patient_id": "ONC-018",
  "uroven": 3,
  "doporuceny_krok": "telekonzultace",
  "upozornit_tym": true,
  "doporuceny_kontakt": "telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h",
  "klicove_nalezy": ["rozpor: dotazník bez průjmu, zpráva ~6 stolic za 24 h", "FOLFIRI (irinotekan), C1 D5", "69 let, slabost"],
  "varovne_priznaky": ["průjem 4–6 stolic nad normál při irinotekanu"],
  "zduvodneni": "Zpráva má přednost před dotazníkem. Opožděný průjem po irinotekanu může rychle vést k dehydrataci; posouzení lékařem týž den.",
  "doporuceni_pro_pacienta": "Píšete, že máte hnačku asi 6× za deň – je to tak? Užite loperamid podľa schémy, ktorú máte od lekára, a pite. Ešte dnes vám zavolá lekár. Ak budete mať horúčku, krv v stolici alebo závrate, volajte ihneď 155.",
  "doplnujici_otazka": "Píšete, že máte hnačku asi 6× za deň – je to tak?",
  "pravidla": ["O-DIARRHEA-RISK", "C-CONTRADICTION"],
  "dukazy": [{"zdroj": "zprava", "checkin_id": "ONC-018-C03", "citace": "od vcera mam hnacku asi 6 krat"}],
  "jistota": "stredni",
  "sla_do": "2026-09-11T10:30:00+02:00",
  "verze": "engine 0.1.0, rules 2026-10-16"
}
```

### 8.11 Doctor summary (readable in 30 seconds)

Generated at every escalation to level ≥ 3, on the morning of each application (cycle D1) for patients on active treatment, weekly for palliative patients, and on demand. The structure follows `vzorove_souhrny_pro_lekare.md`; example adapted from the package:

```text
ONC-007 · Hana D., 55 let · souhrn při eskalaci (2026-09-10, 07:35)
Proč teď: nově ortopnoe a +3 kg za 7 dní u pacientky na trastuzumabu po antracyklinech. ORANŽOVÁ – telekonzultace dnes.
Léčba: trastuzumab s.c. à 21 dní (C12), letrozol. Poslední ECHO před 3 měsíci: LVEF 58 % (před léčbou 64 %).
Vývoj: 3. 9. 83,4 kg, večer oteklé kotníky → 7. 9. 85,0 kg, otoky i ráno → 10. 9. 86,4 kg, tep 94 (naměřeno), „spí na dvou polštářích“ (pacientka).
Nehlásí: dušnost v klidu, bolest na hrudi, mdlobu.
K posouzení lékařem: možná kardiotoxicita – neodkládat vyšetření plánované na 14. 9.
```

- One top sentence: what matters now and what is expected from the doctor.
- Trends instead of all values; every claim traceable to a dated record (a link in the UI).
- Sources marked: (pacient), (naměřeno), (odhad systému).
- No diagnosis, no treatment proposal — only „k posouzení“; nothing from after `as_of`; target ≤ 120 words.
- Build: code assembles a list of facts with references → the LLM writes the text from those facts only → a validator checks that every number and date in the text exists in the facts; otherwise the deterministic layout is used.

### 8.12 Alerts to the team

- Level 2–4 → FHIR Task (status `requested`, priority by level, owner = monitoring centre or, out of hours, the on-duty doctor; SLA in `restriction.period.end`; `reasonReference` → RiskAssessment) + a Flag on the patient + an outbound Interoperability message to the MEDDI mock.
- Lifecycle `requested → accepted → in-progress → completed`; every action is appended to `Task.note` and written as a team event, which feeds the „team already acting“ rule.
- Level 4: banner and sound in the clinician web, SLA timer of 15 minutes.
- A new escalation of the same patient updates the open Task (raises priority, appends evidence) instead of creating a duplicate.

## 9. AI navigator chat (new compared with Hlídač)

The patient or caregiver can write (or speak) to the navigator at any time. Every message runs through the same triage pipeline as a check-in, so a chat message escalates exactly like a questionnaire, and the agent can never lower a level set by the engine.

**What it does**

1. **Answers questions** from approved sources only: patient-facing chunks in `Guide_Chunk` (MEDDI questionnaire warnings, plain-language versions of the triage rules, team-approved education texts) plus the patient's own care plan and medicine list.
2. **Asks follow-ups** when the engine needs them (contradiction, missing count, unclear severity) and feeds the answer back into triage.
3. **Runs a conversational check-in** (COULD): the same items as `nezadouci_ucinky`, saved as a QuestionnaireResponse with `source = chat`.
4. **Hands over:** at levels 2–4 the reply starts with the deterministic next-step card (contact, time, call buttons); LLM text follows only if the validator passes.

**Pipeline per message:** message → `nlu` facts → `triage_engine` (`source: chat`, context as of now) → if level ≥ 2, alert + next-step card → LLM answer with RAG and tools → validator → Communication stored in IRIS.

**MCP tools (IRIS MCP server)**

| Tool | Does | Guard |
| --- | --- | --- |
| `get_patient_context(patient_id, as_of)` | regimen, cycle day, medicines with classes, allergies, last labs, open Tasks | read-only, pseudonymised |
| `get_recent_checkins(patient_id, n)` | last n check-ins with levels and findings | read-only |
| `get_trend(patient_id, metric, days)` | weight, BP, pulse, temperature, glucose, stools, pain | read-only |
| `search_guidance(query, lang)` | top 5 patient chunks from Vector Search | `Audience = patient` only |
| `get_contact(level, at)` | the right contact and opening hours | from the router config |
| `ask_followup(question)` | posts a follow-up question to the patient | one open question at a time |
| `escalate(level, reason, evidence)` | creates or raises a Task | can only raise, never lower |

**Agent rules (system prompt in Czech)**

- Never diagnose: „Mám kolitidu?“ → it cannot say; it offers the team.
- Never change doses: „Můžu mamince dát další Oramorph?“ → only what the prescription says („10 mg, max 6× denně“), nothing beyond it without the team; refractory pain → palliative doctor today.
- Emergencies → 155 immediately; out-of-hours contacts come from `get_contact`.
- The patient's language, at most 4 short sentences, no jargon („horečka v době, kdy máte málo bílých krvinek“, not „febrilní neutropenie“).
- Address the caregiver when they write; no names or birth dates are sent to the LLM.

**Example (ONC-001, Wednesday 21:52, D10 after AC)**

> **Pacientka:** mam 38,4 a trese me zima
>
> **Navigátor** (red card): Teplota 38,4 °C během chemoterapie potřebuje okamžité vyšetření. Volejte hned sloužícího lékaře MOÚ 724 590 848; pokud se nedovoláte, volejte 155 nebo jeďte na urgentní příjem. Paralen si neberte, dokud vás nevyšetří lékař. \[Volat 724 590 848\] \[Volat 155\]

**Navigator output contract**

```json
{
  "reply_text": "…",
  "lang": "cs",
  "level_card": {"uroven": 4, "kontakt": "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)", "buttons": ["tel:724590848", "tel:155"]},
  "followup_question": null,
  "facts": [{"type": "temperature_c", "value": 38.4, "quote": "mam 38,4"}, {"type": "chills", "value": true, "quote": "trese me zima"}],
  "cites": ["guide:pravidla_triaze#horecka"],
  "escalated": true
}
```

**Voice (bonus, COULD):** a mic button in the chat → Web Speech API (`cs-CZ`, `sk-SK`) or an EU speech service → the same pipeline; the reply can be read aloud. Large buttons help patients with low digital literacy (ONC-018).

## 10. Screens: the Hlídač design plus the chat

Reuse the Hlídač design 1:1 in layout and components, replace its yes/no warning with the 4 triage colours, and add the navigator chat. UI copy is Czech (Slovak for `jazyk: sk`). Design reference: [Hlídač design canvas](https://claude.ai/artifact/CBbqidsiGWstatBMZjvkRS) — boards Pacient (Domů, Dotazník, Výsledek bez varování, Varovný příznak), Lékař A (fronta + detail), Lékař B (monitoring), B2 (klik na graf: den), B3 (klik na hlášení: příznak).

**Triage colours** — Material 3 custom colours harmonised to the seed `#0E6B5C` (suggested values; never colour alone, always icon + label):

| Level | Token | Container / on-container | Icon | Label |
| --- | --- | --- | --- | --- |
| 1 | `triage-green` | `#D8F2E0` / `#0B5132` | check\_circle | Zelená · Další sledování |
| 2 | `triage-yellow` | `#FFF0C2` / `#5A4300` | info | Žlutá · Ozve se tým |
| 3 | `triage-orange` | `#FFDCC5` / `#6B2E00` | call | Oranžová · Telekonzultace dnes |
| 4 | `triage-red` | `#FFDAD6` / `#8C1D18` (error `#B42318`) | emergency | Červená · Volejte ihned |

**Patient app** — phone, 360–430 px; bottom navigation Domů · Check-in · Navigátor · Historie

| Id | Screen | Hlídač board | What changes |
| --- | --- | --- | --- |
| P1 | Domů | Domů | today's check-in card (due / done), last result chip, cycle chip „C2 · den 10“, contacts card (monitorovací centrum Po–Pá 7:00–15:30, sloužící lékař 724 590 848, 155), FAB „Napsat navigátorovi“ |
| P2 | Check-in | Dotazník | MEDDI items in exact wording with `enableWhen` branching, one question per screen; vitals step (teplota, TK, tep, váha, glykémie, SpO2 optional); „Chcete nám něco napsat?“; photo; switch „Vyplňuji za blízkou osobu“ |
| P3 | Výsledek – zelená | Výsledek bez varování | green card, advice, „Kdy se ozvat dřív“, link to the navigator |
| P4 | Výsledek – žlutá / oranžová / červená | Varovný příznak | colour card, one plain sentence why, the step with its time, big `tel:` buttons, what to do meanwhile (pre-agreed only), follow-up question if any; red = full-screen card |
| P5 | Navigátor (new) | — | M3 chat: bubbles, quick-reply chips, attach photo, mic (bonus), sticky next-step card when level ≥ 2, caregiver header „Píšete za: maminka“ |
| P6 | Historie (new) | — | timeline of check-ins with level chips, team replies and chat |

**Clinician web** — desktop ≥ 1280 px, navigation rail

| Id | Screen | Hlídač board | What changes |
| --- | --- | --- | --- |
| C1 | Fronta | Lékař A | sorted by level, then SLA; columns level · patient · regimen + cycle day · why (one line) · SLA countdown · status; badge „mimo pracovní dobu → sloužící lékař“; right panel = 30-second summary + evidence |
| C2 | Monitoring | Lékař B | KPI tiles (today by level, open Tasks, SLA breached, missed check-ins); stacked bars of check-ins by level per day; symptom bars from the MEDDI questionnaire |
| C3 | Den | B2 | click a day → patients with level ≥ 2 that day, reason, status, action |
| C4 | Příznak | B3 | click a symptom → patients, grade-trend sparkline, risk badges (IO, FP, irinotekan, antikoagulace) |
| C5 | Detail pacienta | detail in A | header (age, diagnosis, regimen, cycle / nadir, risk badges, advance directive); timeline (check-ins, labs, team events, chat); trend charts (weight, BP, temperature, stools, pain); triage explanation (rules fired, quotes, sources); actions Převzít · Zavolat · Telekonzultace · Uzavřít s poznámkou · Vytvořit souhrn |
| C6 | Replay a evaluace (new) | — | dataset and patient picker, play / step / speed, clock with the working-hours band, predicted vs ground truth per check-in, 4×4 confusion matrix, metrics (§13) |

**Material 3 + PWA (from Hlídač):** MUI themed with M3 tokens from Material Theme Builder (seed `#0E6B5C`, error `#B42318`); `@material/web` where pure M3 components are needed; M3 type scale, 48 dp touch targets, light and dark theme. PWA via `vite-plugin-pwa`: manifest „MEDDI navigátor“, standalone display, offline shell that keeps the last result and working `tel:` links, an offline queue for check-ins (background sync), Web Push for reminders and team replies (iOS 16.4+ only for installed PWAs).

## 11. API and MEDDI integration proposal

Our REST API serves the PWA and the clinician web; a separate proposed contract shows how the same engine plugs into MEDDI Onco — events in, structured outputs back. In the prototype the MEDDI side is the JSON adapter.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/patients` | list with last level and open Task |
| GET | `/api/patients/{id}/context?as_of=` | the context snapshot the engine used |
| GET | `/api/patients/{id}/timeline?as_of=` | check-ins, labs, team events, chat |
| POST | `/api/checkins` | check-in in the MEDDI JSON shape → triage output (§8.10) |
| GET | `/api/checkins/{id}/triage` | stored triage output |
| POST | `/api/chat/{patient_id}/messages` | chat turn; SSE variant `/stream` |
| GET | `/api/queue?status=open` | monitoring-centre queue (Tasks) |
| POST | `/api/tasks/{id}/action` | `accept` · `call` · `telekonzultace` · `close` (+ note) → team event |
| GET | `/api/patients/{id}/summary?as_of=&reason=` | doctor summary (Composition) |
| GET | `/api/stats/daily?from=&to=` | dashboard aggregates |
| POST | `/api/replay` | start a replay `{dataset, patients?, speed}` |
| GET | `/api/replay/{run}/events` | SSE stream of outputs |
| GET | `/api/eval/{run}` | metrics, confusion matrix, error list |
| GET | `/api/health` | IRIS, LLM and MCP status |

**Proposed MEDDI ↔ navigator contract**

| Direction | Event / call | Payload |
| --- | --- | --- |
| MEDDI → us | webhook `checkin.submitted` | check-in JSON as in the package, or a FHIR QuestionnaireResponse Bundle |
| MEDDI → us | webhook `message.created` | text, author (patient / relative), language |
| MEDDI → us | webhook `team.event` | telekonzultace, změna léčby, hospitalizace… |
| us → MEDDI | `GET /patients/{id}/context` | treatment, cycles, medicines, labs, exams, team events (or FHIR reads) |
| us → MEDDI | `POST /requests` | `{patient_id, priority, category, title, why, due_at, summary, evidence[]}` → monitoring-centre queue |
| us → MEDDI | `POST /messages` | `{patient_id, text, lang, buttons[]}` |
| us → MEDDI | `PUT /patients/{id}/summary` | structured summary + rendered text |

Auth via OAuth2 client credentials or mTLS; idempotency key = `checkin_id`; retries with backoff; every call audited.

**Adapter interface**

```python
class MeddiAdapter(Protocol):
    def get_context(self, patient_id: str, as_of: datetime) -> PatientContext: ...
    def iter_checkins(self, patient_ids: list[str] | None = None) -> Iterator[Checkin]: ...
    def create_request(self, triage: TriageOutput, summary: DoctorSummary | None) -> str: ...
    def send_patient_message(self, patient_id: str, text: str, lang: str, buttons: list[Button]) -> None: ...
    def save_summary(self, summary: DoctorSummary) -> None: ...
```

Implementations: `MeddiJsonAdapter` (prototype, reads the package), `IrisFhirAdapter` (our store), `MeddiApiAdapter` (stub for production).

**Production in AWS EU (MEDDI requirement):** everything in one EU region (e.g. eu-central-1) — IRIS for Health on EC2 or EKS, the API on ECS Fargate, the LLM via Amazon Bedrock in the same region or a self-hosted open model on EC2. Private subnets, KMS encryption, CloudWatch audit, no storage at third parties. The LLM gets only the minimum: no names, pseudonymised ids, age bands, relevant medicines. For the prototype any LLM may be used on the synthetic data.

## 12. Seed and replay

`make seed` loads both packages into IRIS as FHIR without the check-ins; `make replay` then feeds the check-ins in time order and builds every context strictly as of the check-in time — exactly how the jury will test.

**Seed steps**

1. Unzip both packages to `data/` (read-only); validate with pydantic models; fail on unknown fields.
2. Load the 4 Questionnaires from `dotazniky_definice.json` (`podminka` „ucinky:1“ → `enableWhen` on `ucinky` = option 1).
3. Per patient one transaction Bundle: Patient, RelatedPerson (if a relative fills in), Conditions, AllergyIntolerance, Consent (advance directive), CarePlan with cycles, MedicationRequests, lab Observations, DiagnosticReports, team events — all with their real timestamps.
4. Labs can instead go through the Interoperability production as HL7v2 ORU^R01 (file drop), to show the InterSystems flow.
5. Build Vector Search: `Guide_Chunk` from `pravidla_triaze.md` (one chunk per rule row or section), questionnaire warnings, README rules and our patient-facing texts; `Checkin_Text` from the dev check-ins.
6. Load `ground_truth/` into `Eval_Expected` only.
7. Demo mode: `make seed NOW=2026-09-10T08:00` also replays everything before that moment, so the UI starts with history.

**Sample HL7v2 lab message (ONC-001, first blood draw)**

```text
MSH|^~\&|LIS|MOU_LAB|MEDDI_NAV|MOU|20260831093000||ORU^R01^ORU_R01|ONC-001-L01|P|2.5.1
PID|1||ONC-001^^^MEDDI^MR||K^Jana||19780101|F
OBR|1||ONC-001-L01|58410-2^CBC panel - Blood by Automated count^LN|||20260831093000
OBX|1|NM|6690-2^Leukocytes [#/volume] in Blood by Automated count^LN||6.3|10*9/L|4.0-10.0|N|||F
OBX|2|NM|751-8^Neutrophils [#/volume] in Blood by Automated count^LN||3.7|10*9/L|2.0-7.0|N|||F
OBX|3|NM|718-7^Hemoglobin [Mass/volume] in Blood^LN||132|g/L|120-160|N|||F
OBX|4|NM|777-3^Platelets [#/volume] in Blood by Automated count^LN||218|10*9/L|150-400|N|||F
```

The birth date is synthetic (age 48 at the start of monitoring).

**Replay algorithm**

```text
events = all check-ins of the chosen patients, sorted by datum + cas
for c in events:
    ctx = context_builder(c.patient_id, as_of = c.timestamp)
    out = triage(c, ctx)                 # level, step, contact, texts, rules, evidence
    write FHIR: QuestionnaireResponse, Observations, Communication,
                RiskAssessment, Provenance, Task + Flag if level >= 2
    emit an SSE event to the UI
    eval.compare(out, Eval_Expected[c.checkin_id])   # eval module only
```

**Leakage guards (each with a test)**

- Labs, team events and earlier check-ins are visible only with a timestamp ≤ the check-in; exams (date only) only from earlier days.
- The engine never reads `nazev_scenare`, `vychazi_ze_scenare`, `ground_truth/` or `Eval_Expected`.
- `Checkin_Text` retrieval excludes the replayed patient and its scenario variants.
- A unit test fails if any context contains a resource dated after `as_of`.

## 13. Demo script and acceptance criteria

The MVP is accepted when the replay of the dev and extended sets shows **zero under-triaged red**, the critical moments below come out right, and the 6-minute demo runs end to end on one laptop.

**Metrics** (reported for dev and extended separately)

| Metric | Target |
| --- | --- |
| Red recall (GT 4 → predicted 4) | 100 % |
| Orange recall (GT 3 → predicted ≥ 3) | ≥ 95 % |
| Under-triage by 2 or more levels | 0 |
| Under-triage overall (predicted < GT) | ≤ 3 % of check-ins |
| False alarms (GT 1 → predicted ≥ 2) | ≤ 15 % of green check-ins; ≥ 3 reported separately |
| `upozornit_tym` agreement | ≥ 95 % |
| Routing (contact category by working hours) | ≥ 95 %; exact-string match reported |
| Exact level match | ≥ 85 % (informative) |
| Patient texts passing the validator | 100 % (otherwise the template) |
| Latency | triage ≤ 3 s p95; chat first token ≤ 1.5 s |

**Critical moments in the dev set (acceptance tests)**

| Test | Check-in(s) | Expected | Why |
| --- | --- | --- | --- |
| Fever in nadir | ONC-001-C07 (Wed 21:52) | 4, out-of-hours contact | 38.4 °C, chills, D10 after AC |
| Port infection | ONC-008-C09 (Fri 20:45) | 4 | 38.6 °C, chills, redness around the port, R-CHOP |
| Immune colitis within 2 days | ONC-004-C04 → C05 → C06 | 2 → 3 → 4 | 3 → 4 (+ pain) → 8 stools + blood on ipilimumab + nivolumab |
| Vomiting → dehydration, daughter writes | ONC-010-C02 → C03 → C04 | 2 → 3 → 4 | 2× → 5× and no fluids → 7× and no urine > 10 h |
| Mucositis → dehydration | ONC-011-C05, C08, C09 | 3, 3, 4 | liquids only + pain; NRS 7; < 0.5 l a day, oliguria |
| Opioid sleepiness, palliative | ONC-014-C09 | 4 despite the advance directive | somnolence, 8 breaths/min after a dose increase |
| Refractory pain, caregiver | ONC-014-C05 | 3, daughter addressed, no extra doses | NRS 8 after 2 Oramorph doses |
| Creeping heart failure | ONC-007-C06 → C07 → C08 | 2 → 2 → 3 | oedema, +3 kg in 7 days, new orthopnoea on trastuzumab |
| Capecitabine + warfarin | ONC-013-C05, C06 | 3, 3 | grade 2 diarrhoea on capecitabine; gum bleeding and bruises on warfarin |
| Contradiction in Slovak | ONC-018-C03 → C04 | 3 + follow-up in Slovak → 2 | form: no diarrhoea, text: \~6×; then improving |
| FOLFOX diarrhoea in a diabetic | ONC-002-C08 | 3 | 5 stools despite loperamide, metformin |
| Neuropathy before C7 | ONC-002-C12 (Mon 07:10) | 2 + summary before the application | fine-motor neuropathy on oxaliplatin |
| Sunitinib blood pressure | ONC-009-C06, C12 | 3, 2 | 168/102 on antiangiogenic; 106/66 + dizziness in the pause |
| Psychology | ONC-016-C05, C06 | 3, 3 (not 4) | hopelessness; passive death wish without plan or intent |
| Missed check-ins | ONC-017-C06, C07, C08 | 1, 1, 2 | reminder, reminder, team contacts the patient |
| Stable patient | ONC-005 (all) | 1, except C10 = 2 on Sunday → next working day | no false alarms, slow BP rise |

**Demo script (6 minutes)**

1. The problem in one sentence; MEDDI Onco today (questionnaire colours judge each answer alone).
2. Phone: Jana (ONC-001) does the D10 check-in with 38.4 °C → red full-screen card with call buttons; the clinician queue shows a red Task with a 15-minute timer and the summary.
3. Replay console: ONC-004 day by day (yellow → orange → red) with rules and quotes; the summary at escalation matches the sample format.
4. Slovak patient ONC-018: contradiction → follow-up in Slovak → answer → level updated.
5. Daughter of ONC-014 in the chat: „Můžu mamince dát další Oramorph?“ → guardrail, prescription quoted, palliative team contacted.
6. Metrics on dev and extended: red recall 100 %, false alarms, routing; confusion matrix.
7. InterSystems in 60 seconds: FHIR resources in the IRIS portal, an SQL trend query, a Vector Search hit, the MCP tool-call log, the production with an HL7 lab in and an alert out.
8. Integration and AWS EU slide.

## 14. Sources and mentor input

**Challenge and data (uploaded files):** the Rakathon MEDDI Onco challenge deck; the data package `README.md`, `docs/pravidla_triaze.md` (built on the UKONS 24h Triage Tool, CTCAE v5 and PRO-CTCAE), `docs/dotazniky_definice.json`, `docs/vzorove_souhrny_pro_lekare.md`, `docs/pacientska_cesta_meddi_onco.md`; the extended-set `README.md`. Previous spec: [Hlídač nežádoucích účinků — MVP spec](https://claude.ai/code/artifact/0c235f3f-30a4-4c35-9635-59f789c8b451).

**Mentor input (Alina Pirshtuk, Slack — given for Hlídač, applies here too)**

- Write adverse events with grade and source: „Nevolnost G1 (pacient)“, „Anémie G2 (odběr)“; we add „(odhad systému)“ for system estimates.
- Grading reference: CTCAE v6. The package thresholds follow v5; for evaluation the package wins.
- Drug information: SÚKL. Immunotherapy toxicities: ESMO and ČOS Modrá kniha, chapter 45. Supportive and palliative care: ESMO.
- Dataset questions: Ondřej Hoferek (InterSystems mentor).

**Links**

- [CTCAE v6.0](https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events/ctcae-v6.pdf)
- [SÚKL – přehled léčených přípravků](https://prehledy.sukl.cz/prehled_leciv.html#/)
- [ESMO – management of toxicities from immunotherapy](https://www.esmo.org/guidelines/esmo-clinical-practice-guideline-management-of-toxicities-from-immunotherapy)
- [ESMO – supportive and palliative care guidelines](https://www.esmo.org/guidelines/esmo-clinical-practice-guidelines-supportive-and-palliative-care)
- [ČOS Modrá kniha, kap. 45 – imunitně podmíněné vedlejší účinky](https://www.linkos.cz/lekar-a-multidisciplinarni-tym/personalizovana-onkologie/modra-kniha-cos/aktualni-vydani-modre-knihy/32-45-imunitne-podminene-vedlejsi-ucinky-po-moderni-imunoterapii-s-checkpoint-in/)
- [InterSystems Challenge at Rakathon 2026](https://developer.intersystems.com/intersystems-challenge-at-rakathon-2026/)
- [FHIR-AI-Hackathon-Kit](https://github.com/intersystems-community/FHIR-AI-Hackathon-Kit) — setup `V1/Tutorial/0-FHIR-server-setup.md`; agents `V2/Tutorials/5-ai/5.1-agents-and-tools.ipynb`; MCP `V2/Tutorials/5-ai/5.2-mcp-server.ipynb`
- [InterSystems docs – HL7 → SDA → FHIR](https://docs.intersystems.com/healthconnectlatest/csp/docbook/Doc.View.cls?KEY=AHXDT)
- [Vector Search example (InterSystems Community)](https://community.intersystems.com/node/586569)
- [IRIS Community Edition limits](https://community.intersystems.com/node/526081)

## 15. Open questions

None of these blocks the build: each has a default the engine uses until MEDDI or a mentor answers.

| Question (for MEDDI / mentors) | Default until answered |
| --- | --- |
| Out-of-hours orange: the data has no example (all 105 oranges fall in working hours). Exact contact text? | „sloužící lékař MOÚ 724 590 848 – ihned“ |
| Public holidays: the ground truth treats 28. 9. 2026 as a working day. Use the MOÚ calendar in production? | off for evaluation, on in production |
| Missed check-ins of high-risk patients: the README says „earlier“ — how much earlier? | 2 missed during nadir D7–14 or on immunotherapy → 2 |
| The psycho-oncology screening has no scoring key. Thresholds? | `uzkost` or `depresivita` ≥ 6, or `zvladani` ≤ 3 → 2; `sebevrazda` = Ano → 3 |
| SpO2 is used by the rules but missing in the data. Field name in MEDDI? | `spo2`, source `oxymetr` |
| 24 h palliative line or hospice number for palliative patients? | generic text + 155 |
| Pre-agreed instructions (loperamide scheme, antipyretics): will MEDDI provide them as care-plan items? | quote only the `leky` text, verbatim |
| Fever ≥ 38 °C outside the chemotherapy window (hormonal, TKI, immunotherapy only): which level? | 2; ≥ 39 °C → 3; ≥ 40 °C → 4 (R-HYPERPYREXIA) |
| Which LLM in AWS EU is acceptable to MEDDI (Bedrock model, data processing agreement)? | Amazon Bedrock in an EU region |
| Voice bonus: input only, or reading answers aloud too? (deck contact: Jiří Pecina) | both, as a COULD |

## 16. Non-functional requirements, deliverables, priorities, timeline

**Non-functional**

- **Safety:** rules live in a versioned `rules.yaml` (id, minimum level, source); every rule has positive, boundary and negative unit tests; a property test proves no LLM output lowers a level; if the LLM or IRIS is down, the engine runs rules-only and escalates when unsure.
- **Explainability:** every output lists fired rules, findings and verbatim quotes with their source record; Provenance in IRIS.
- **Privacy:** synthetic data only; the LLM never gets names or birth dates; logs without free text by default; production in AWS EU.
- **Performance:** triage ≤ 3 s p95; replay of all 1 320 check-ins ≤ 10 min with the LLM, ≤ 1 min rules-only.
- **Accessibility:** WCAG 2.1 AA, scalable text, 48 dp targets, plain language a primary-school reader understands.
- **Localisation:** Czech by default, Slovak; all strings in i18n files.
- **IRIS Community limits:** at most 4 pooled connections, batched FHIR writes.

**Deliverables**

1. `docker compose up` → IRIS + API + web with seeded data.
2. Patient PWA, clinician web, replay console.
3. Evaluation report for dev and extended: metrics, confusion matrix, error list (JSON + page).
4. README: setup, architecture, InterSystems usage, rules table.
5. Integration proposal and AWS EU slide; pitch deck; backup demo video.

**Priorities**

| Priority | Items |
| --- | --- |
| MUST | FHIR seed in IRIS; triage engine with all hard rules, modifiers, trends and gaps; routing by working hours; replay + metrics; patient check-in + result; clinician queue + detail + summary; navigator chat (Q&A, follow-up, escalation); validator; Vector Search RAG; MCP tools; one inbound + one outbound Interoperability flow |
| SHOULD | monitoring dashboard + drill-downs; caregiver mode; Slovak; PWA offline + push; Provenance; Embedded Python jobs |
| COULD | voice; conversational check-in; IntegratedML risk hint; photo analysis |
| WON'T | real MEDDI API, real patients, real login, eRecept, video calls |

**Timeline** (hours from the start; fit to the Rakathon schedule)

| Hours | Work | Exit check |
| --- | --- | --- |
| 0–4 | IRIS up, data models, FHIR seed | 114 patients readable over FHIR |
| 4–12 | rules engine, router, replay, metrics | red recall 100 % on dev, rules-only |
| 12–20 | NLU (LLM + lexicon), contradictions, trends, gaps; tuning on the extended set | §13 targets on both sets |
| 20–28 | patient PWA (P1–P4), clinician queue and detail (C1, C5) | check-in → alert visible end to end |
| 28–34 | navigator chat + MCP + Vector Search; doctor summary | demo steps 4–5 work |
| 34–40 | dashboard (C2–C4), HL7 lab flow, outbound alert, PWA polish | InterSystems demo step works |
| 40–44 | freeze, evaluation report, pitch, backup video | full demo under 6 minutes |
