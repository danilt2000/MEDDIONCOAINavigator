# Interoperability: HL7v2 labs in, alerts out

`MEDDI.Production` runs in the `FHIRSERVER` namespace of the `meddi-iris` container (spec §6: one inbound and one outbound flow).

```text
inbound   iris/inbox/*.hl7 ─► MEDDI.LabHL7.Service ─► MEDDI.LabHL7.Process ─► MEDDI.SDA3ToFHIR ─► HS.FHIRServer.Interop.Operation ─► /fhir/r4
          (ORU^R01 2.5.1)     HL7 file service       HL7 -> SDA3            SDA3 -> FHIR Bundle   transaction into the repository

outbound  app/services/side_effects.py ─► send_alert_via_iris(payload) ─► MEDDI.Alert.Service ─► MEDDI.Alert.Operation ─► POST /mock/meddi/requests
          (every task of level >= 2)       native API, async            Ens.StringRequest      EnsLib.HTTP.OutboundAdapter
```

## Inbound: HL7v2 lab results to FHIR

| Host | Class | What it does |
|---|---|---|
| `MEDDI.LabHL7.Service` | `EnsLib.HL7.Service.FileService` | polls `/home/irisowner/meddi/inbox/*.hl7` (= `iris/inbox` on the host), schema 2.5.1, UTF-8; processed files move to `iris/inbox/done/` |
| `MEDDI.LabHL7.Process` | ours | `HS.Gateway.HL7.HL7ToSDA3.GetSDA()` → SDA3; passes `PatientResourceId` = PID-3 (`ONC-001`) |
| `MEDDI.SDA3ToFHIR` | `HS.FHIR.DTL.Util.HC.SDA3.FHIR.Process` | SDA3 → transaction Bundle with `TransformClass` = `MEDDI.LabHL7.Transform`, metadata set HL7v40, endpoint `/fhir/r4` |
| `HS.FHIRServer.Interop.Operation` | standard | runs the transaction against the local FHIR server |

Per blood draw the repository gets one lab `Observation` per OBX (category `laboratory`, LOINC code, value in UCUM-style units, reference range, `effectiveDateTime` with the Prague offset), plus a `ServiceRequest` and a `DiagnosticReport` that lists the Observations, and the `Organization`s `MOU_LAB` and `MEDDI`.

**How the HL7 data lines up with the seeded data (`app/fhir`)** (`MEDDI.LabHL7.Transform`, run after the standard transform):

- Patient: every reference points to `Patient/{PID-3}`, the id the seed uses (`Patient/ONC-001`). If that Patient exists, the HL7 Patient is dropped from the Bundle, so the seeded one is never overwritten. If it does not exist yet, it is created under that id from PID (name, sex, birth date, identifier `urn:meddi:patient|ONC-001`), and a later seed overwrites it in place. So the HL7 flow creates no duplicate Patient.
- Lab Observations get the seed's identifier `urn:meddi:lab|{odber_id}-{kod}` (e.g. `ONC-001-L01-leu`). Every POST in the Bundle is a conditional create (`ifNoneExist` on its identifier). A lab the seed already loaded, or a file dropped twice, adds nothing new. The DiagnosticReport then points to the existing Observations.
- Caveats: if a Patient with the same identifier was ever created under another id (for example by a POST without an id), it stays a separate duplicate, because the HL7 flow only looks at `Patient/{PID-3}`. If two resources match one `ifNoneExist` (for example two `Organization`s with identifier `MEDDI`), the server answers 412 and that file fails; you see the error in the message trace.
- To see a **new** Observation appear in the demo, drop a draw that the seed has not loaded yet: `python -m app.interop.hl7 --patient ONC-001 --new` re-sends the last draw as a new one taken now (new `odber_id` `…-N<hhmmss>`), and 10 new lab Observations appear on `Patient/ONC-001`. When the seed has loaded everything, the drop still shows the full trace, and only the ServiceRequest and DiagnosticReport are new.

**Message format** (`backend/app/interop/hl7.py`, one message per `odber_id`). This is the spec §12 sample plus what `HL7ToSDA3` needs:

```text
MSH|^~\&|LIS|MOU_LAB|MEDDI_NAV|MOU|20260831093000+0200||ORU^R01^ORU_R01|ONC-001-L01|P|2.5.1||||||UNICODE UTF-8
PID|1||ONC-001^^^MEDDI^MR||K^Jana||19780101|F
ORC|RE|ONC-001-L01|ONC-001-L01||||||||||||||||||||||||||LAB
OBR|1|ONC-001-L01|ONC-001-L01|26436-6^Laboratory studies (set)^LN|||20260831093000+0200||||||||||||||||||F
OBX|1|NM|6690-2^Leukocytes [#/volume] in Blood by Automated count^LN||6.3|10*9/L|4-10|N|||F|||20260831093000+0200
```

The `ORC` segment with ORC-29 = `LAB` is required. Without it, `HL7ToSDA3` stores the results only as report text and creates no Observations. Times carry the Europe/Prague offset. Units: `^`→`*`, `µ`→`u`, `/l`→`/L`.

## Outbound: alerts to the MEDDI monitoring centre

- `app.interop.alerts.send_alert_via_iris(payload: dict) -> bool` opens one native-API connection and calls `MEDDI.Alert.Service.Send(json)`, then closes the connection. The call is async inside IRIS: `True` means the alert is queued in the production. It returns `False` and never raises when IRIS is unreachable (after about 2 s) or the production is stopped. `app/services/side_effects.py` calls it in the background for every task of level ≥ 2 and posts directly to the mock if it returns `False`.
- `MEDDI.Alert.Operation` POSTs the JSON (UTF-8) with `EnsLib.HTTP.OutboundAdapter`. The target is a production setting: adapter `HTTPServer` / `HTTPPort` / `URL`, default `http://host.docker.internal:8100/mock/meddi/requests`. If the endpoint is down, the operation retries for 15 s (`FailureTimeout`) and logs an error in the event log.
- Mock (`backend/app/api/mock_meddi.py`): `POST /mock/meddi/requests` stores `{id, received_at, payload}` in memory, and `GET /mock/meddi/requests` lists what it received. The list is empty again after an API restart.

## How to run

```sh
docker compose up -d                                   # IRIS for Health + FHIR server (repo root)
sh iris/scripts/install.sh                             # load MEDDI.* classes, (re)start MEDDI.Production, set auto-start
cd backend
PYTHONPATH=. .venv/Scripts/python.exe -m app.interop.hl7 --patient ONC-001          # preview the ORU^R01 messages
PYTHONPATH=. .venv/Scripts/python.exe -m app.interop.hl7 --patient ONC-001 --drop   # drop them into iris/inbox
curl -u SuperUser:SYS "http://localhost:52773/fhir/r4/Observation?identifier=urn:meddi:lab|ONC-001-L02-neu"
curl http://localhost:8100/mock/meddi/requests         # alerts received by the mock (API on 8100)
PYTHONPATH=. .venv/Scripts/python.exe -m pytest tests/interop -q
```

`install.sh` works on a fresh container and can be run again; it also resets the production settings to the class defaults. To send alerts to another API port while testing: `sh iris/scripts/set-alert-target.sh 8103`. Restore it with `... 8100` and do not leave it changed, because everyone's alerts follow this setting. Both scripts accept `CONTAINER=<name>`.

## Portal for the demo (login `SuperUser` / `SYS`)

| What | URL |
|---|---|
| Production configuration (hosts, settings, start/stop) | http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.ProductionConfig.zen?PRODUCTION=MEDDI.Production |
| Message viewer (click a session → visual trace) | http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.MessageViewer.zen |
| Event log (errors, retries) | http://localhost:52773/csp/healthshare/fhirserver/EnsPortal.EventLog.zen |
| FHIR server management | http://localhost:52773/csp/fhir-management/index.html |
| FHIR explorer (browse the Observations) | http://localhost:52773/ui/fhir-explorer/ |

Demo in 60 seconds: open the production page, run `--drop` for a patient, and open the newest session in the message viewer. The visual trace shows HL7 → SDA3 → FHIR transaction. Then show the Observation over FHIR, trigger a level 4 check-in (ONC-001-C07), and show the `MEDDI.Alert.Operation` session and the payload in `GET /mock/meddi/requests`.
