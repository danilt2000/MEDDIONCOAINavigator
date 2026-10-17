"""Read-only look into IRIS for Health for the jury (clinician web #/iris).

The API is public: clients send a query id, never SQL; values go only as bound parameters; at most ROW_LIMIT rows,
a statement timeout, one connection at a time, and nothing about the connection itself in any response.
"""
import json
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Path, Query

from app.config import settings

router = APIRouter(prefix="/api/iris", tags=["iris"])

ROW_LIMIT = 200
PAGE_SIZE = 50
MESSAGE_LIMIT = 100
TIMEOUT_SECONDS = 10
IRIS_DOWN = "IRIS for Health teď není dostupná."
RESOURCE_TYPE = r"^[A-Z][A-Za-z]{1,63}$"
RESOURCE_ID = r"^[A-Za-z0-9.\-]{1,64}$"

QUERIES = [
    {
        "id": "vaha-onc007",
        "title": "Rust váhy ONC-007 na trastuzumabu",
        "description": "Váha přímo z FHIR Observation přes pohled MEDDI.FHIR_Observation (LOINC 29463-7).",
        "sql": "SELECT EffectiveAt, NumValue AS kg FROM MEDDI.FHIR_Observation WHERE PatientRef = 'Patient/ONC-007' "
               "AND Loinc = '29463-7' ORDER BY EffectiveAt",
    },
    {
        "id": "otevrene-ukoly",
        "title": "Otevřené tísňové úkoly",
        "description": "FHIR Task s kódem triage-alert, které ještě nejsou uzavřené, podle konce SLA.",
        "sql": "SELECT PatientRef, Priority, OwnerName, SlaEnd FROM MEDDI.FHIR_Task WHERE Code = 'triage-alert' "
               "AND Status <> 'completed' ORDER BY SlaEnd",
    },
    {
        "id": "pravidlo-triaze",
        "title": "Které pravidlo spustilo triáž u pacienta",
        "description": "Výsledky triáže ONC-004 (MEDDI.Triage_Result) spojené s tabulkou pravidel; operátor [ znamená „obsahuje“.",
        "sql": "SELECT t.CheckinId, t.TriageLevel, r.RuleId, r.Expr FROM MEDDI.Triage_Result t JOIN MEDDI.Triage_Rule r "
               "ON t.RuleIds [ r.RuleId WHERE t.PatientId = 'ONC-004'",
    },
    {
        "id": "surovy-json",
        "title": "Surové FHIR JSON",
        "description": "Prvních 20 živých zdrojů tak, jak je IRIS ukládá (JsonAdvSQL, tabulka HSFHIR_X0001_R.Rsrc).",
        "sql": "SELECT TOP 20 ResourceType, Id, ResourceString FROM HSFHIR_X0001_R.Rsrc WHERE Deleted = 0",
    },
    {
        "id": "vaha-json-table",
        "title": "Váha ONC-007 přímo přes JSON_TABLE",
        "description": "Stejná řada bez pohledu: JSON_TABLE nad uloženým JSON zdroje.",
        "sql": "SELECT j.measured, j.kg\n"
               "FROM HSFHIR_X0001_R.Rsrc r, JSON_TABLE(r.ResourceString, '$' COLUMNS (\n"
               "    patient VARCHAR(40) PATH '$.subject.reference', measured VARCHAR(40) PATH '$.effectiveDateTime',\n"
               "    loinc VARCHAR(20) PATH '$.code.coding[0].code', kg NUMERIC(6,1) PATH '$.valueQuantity.value')) j\n"
               "WHERE r.ResourceType = 'Observation' AND r.Deleted = 0 AND j.loinc = '29463-7' AND j.patient = 'Patient/ONC-007'\n"
               "ORDER BY j.measured",
    },
    {
        "id": "vaha-index",
        "title": "Váha ONC-007 přes vyhledávací indexy FHIR",
        "description": "Indexové tabulky FHIR serveru (HSFHIR_X0001_S); časy jsou v UTC, hodnota je rozsah podle přesnosti.",
        "sql": "SELECT o.date_Start, (v.value_ValueLow + v.value_ValueHigh) / 2 AS kg\n"
               "FROM HSFHIR_X0001_S.Observation o\n"
               "JOIN HSFHIR_X0001_S_Observation.code c ON c.Key = o.Key\n"
               "JOIN HSFHIR_X0001_S_Observation.valueQuantity v ON v.Key = o.Key\n"
               "WHERE c.value_System = 'http://loinc.org' AND c.value_Value = '29463-7' AND o.patient_RelativeRef = 'Patient/ONC-007'\n"
               "ORDER BY o.date_Start",
    },
    {
        "id": "horecky",
        "title": "Horečky od 38 °C",
        "description": "Naměřené teploty (LOINC 8310-5) od 38 °C u všech pacientů.",
        "sql": "SELECT PatientRef, EffectiveAt, NumValue AS celsius, Device FROM MEDDI.FHIR_Observation\n"
               "WHERE Loinc = '8310-5' AND NumValue >= 38 ORDER BY EffectiveAt",
    },
    {
        "id": "tlak-onc009",
        "title": "Krevní tlak ONC-009",
        "description": "Systolický a diastolický tlak z panelu LOINC 85354-9.",
        "sql": "SELECT EffectiveAt, Systolic, Diastolic FROM MEDDI.FHIR_Observation\n"
               "WHERE PatientRef = 'Patient/ONC-009' AND Loinc = '85354-9' ORDER BY EffectiveAt",
    },
    {
        "id": "nizke-neutrofily",
        "title": "Nízké neutrofily",
        "description": "Laboratorní neutrofily (LOINC 751-8) s příznakem L u všech pacientů.",
        "sql": "SELECT PatientRef, EffectiveAt, NumValue FROM MEDDI.FHIR_Observation\n"
               "WHERE Loinc = '751-8' AND Interpretation = 'L' ORDER BY PatientRef, EffectiveAt",
    },
    {
        "id": "triaze-podle-stupne",
        "title": "Triáže podle stupně",
        "description": "FHIR RiskAssessment navigátoru spočítané podle stupně 1–4.",
        "sql": "SELECT TriageLevel, COUNT(*) AS Total FROM MEDDI.FHIR_Risk GROUP BY TriageLevel",
    },
    {
        "id": "evaluace",
        "title": "Evaluace: očekávaný a predikovaný stupeň",
        "description": "Referenční stupně (MEDDI.Eval_Expected) proti výsledkům enginu (MEDDI.Triage_Result).",
        "sql": "SELECT e.TriageLevel AS expected, t.TriageLevel AS predicted, COUNT(*) AS Total FROM MEDDI.Eval_Expected e\n"
               "JOIN MEDDI.Triage_Result t ON t.CheckinId = e.CheckinId GROUP BY e.TriageLevel, t.TriageLevel",
    },
]
QUERIES_BY_ID = {query["id"]: query for query in QUERIES}

TABLES = [
    ("MEDDI.Triage_Rule", "pravidla triáže z rules.yaml"),
    ("MEDDI.Triage_Result", "výsledek každé triáže, zapisuje backend při check-inu"),
    ("MEDDI.Drug_Class", "skupiny léků podle názvů v datech"),
    ("MEDDI.Eval_Expected", "referenční stupně pro evaluaci"),
    ("MEDDI.Eval_Run", "běhy evaluace"),
    ("MEDDI.Guide_Chunk", "úryvky doporučení pro Vector Search"),
    ("MEDDI.Checkin_Text", "texty check-inů pro Vector Search"),
    ("MEDDI.FHIR_Observation", "pohled: Observation z FHIR úložiště"),
    ("MEDDI.FHIR_Risk", "pohled: RiskAssessment z FHIR úložiště"),
    ("MEDDI.FHIR_Task", "pohled: Task z FHIR úložiště"),
]

MESSAGE_COLUMNS = ("ID, TimeCreated, SessionId, SourceConfigName, TargetConfigName, MessageBodyClassName, "
                   "%EXTERNAL(Status), %EXTERNAL(Type), IsError")
MESSAGE_BODIES = {
    "Ens.StringRequest": "SELECT StringValue FROM Ens.StringRequest WHERE ID = ?",
    "EnsLib.HL7.Message": "SELECT RawContent FROM EnsLib_HL7.Message WHERE ID = ?",
}

# ponytail: one explorer connection at a time, so a busy jury cannot eat the Community Edition licence units
_lock = threading.Lock()


def _open():
    import iris

    return iris.connect(settings.iris_host, settings.iris_port, settings.iris_namespace,
                        settings.iris_user, settings.iris_password, timeout=2)


@contextmanager
def _connection():
    with _lock:
        try:
            connection = _open()
        except Exception:
            raise HTTPException(503, IRIS_DOWN)
        try:
            yield connection
        except HTTPException:
            raise
        except Exception as error:
            sql_error = str(error)[:400] if "SQLCODE" in str(error) else "spojení s IRIS bylo přerušeno"
            raise HTTPException(502, f"Dotaz v IRIS selhal: {sql_error}")
        finally:
            connection.close()


def _value(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _select(connection, sql: str, params: list | None = None, limit: int = ROW_LIMIT) -> tuple[list[str], list[list], bool]:
    cursor = connection.cursor()
    try:
        cursor.setQueryTimeout(TIMEOUT_SECONDS)
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description or []]
        rows = list(cursor.fetchmany(limit + 1)) if columns else []
        return columns, [[_value(value) for value in row] for row in rows[:limit]], len(rows) > limit
    finally:
        cursor.close()


def _utc(value) -> str | None:
    return str(value)[:19].replace(" ", "T") + "Z" if value else None


def _production(connection) -> dict | None:
    try:
        import iris

        director = iris.createIRIS(connection)
        name = director.classMethodValue("Ens.Director", "GetActiveProductionName")
        running = bool(director.classMethodValue("Ens.Director", "IsProductionRunning"))
        _, items, _ = _select(connection, "SELECT Name, ClassName, Enabled FROM Ens_Config.Item WHERE Production = ? ORDER BY Name", [name])
        _, ((messages, last),), _ = _select(connection, "SELECT COUNT(*), MAX(TimeCreated) FROM Ens.MessageHeader")
    except Exception:
        return None
    return {
        "name": name,
        "running": running,
        "items": [{"name": item, "class_name": class_name, "enabled": bool(enabled)} for item, class_name, enabled in items],
        "messages": messages,
        "last_message": _utc(last),
    }


def _message(row: list) -> dict:
    message_id, created, session, source, target, body_class, status, kind, error = row[:9]
    return {"id": message_id, "time": _utc(created), "session": session, "source": source, "target": target,
            "body_class": body_class, "status": status, "type": kind, "error": bool(error)}


@router.get("/overview")
def overview() -> dict:
    with _connection() as connection:
        _, ((namespace, version),), _ = _select(connection, "SELECT $NAMESPACE, $ZVERSION")
        _, fhir, _ = _select(connection, "SELECT %EXACT(ResourceType), COUNT(*) AS Total FROM HSFHIR_X0001_R.Rsrc "
                                         "WHERE Deleted = 0 GROUP BY %EXACT(ResourceType) ORDER BY Total DESC")
        tables = []
        for name, description in TABLES:
            try:
                rows = _select(connection, f"SELECT COUNT(*) FROM {name}")[1][0][0]
            except Exception:
                rows = None
            tables.append({"name": name, "description": description, "rows": rows})
        return {
            "namespace": namespace,
            "version": version,
            "fhir": [{"type": resource_type, "count": count} for resource_type, count in fhir],
            "tables": tables,
            "production": _production(connection),
        }


@router.get("/queries")
def queries() -> list[dict]:
    return QUERIES


@router.post("/queries/{query_id}/run")
def run_query(query_id: str) -> dict:
    query = QUERIES_BY_ID.get(query_id)
    if query is None:
        raise HTTPException(404, "Neznámý dotaz.")
    with _connection() as connection:
        started = time.monotonic()
        columns, rows, truncated = _select(connection, query["sql"])
        return {"columns": columns, "rows": rows, "truncated": truncated,
                "elapsed_ms": round((time.monotonic() - started) * 1000)}


@router.get("/fhir")
def fhir_resources(resource_type: str = Query(alias="type", pattern=RESOURCE_TYPE),
                   page: int = Query(0, ge=0, le=10_000)) -> dict:
    with _connection() as connection:
        total = _select(connection, "SELECT COUNT(*) FROM HSFHIR_X0001_R.Rsrc WHERE ResourceType = ? AND Deleted = 0",
                        [resource_type])[1][0][0]
        _, rows, _ = _select(
            connection,
            "SELECT ResourceId, LastModified, VersionId FROM HSFHIR_X0001_R.Rsrc WHERE ResourceType = ? AND Deleted = 0 "
            f"ORDER BY LastModified DESC, ID DESC LIMIT {PAGE_SIZE} OFFSET {page * PAGE_SIZE}",
            [resource_type],
        )
    return {
        "type": resource_type,
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "items": [{"id": resource_id, "last_modified": modified, "version": str(version)} for resource_id, modified, version in rows],
    }


@router.get("/fhir/{resource_type}/{resource_id}")
def fhir_resource(resource_type: str = Path(pattern=RESOURCE_TYPE), resource_id: str = Path(pattern=RESOURCE_ID)) -> dict:
    with _connection() as connection:
        _, rows, _ = _select(connection, "SELECT ResourceString FROM HSFHIR_X0001_R.Rsrc "
                                         "WHERE ResourceType = ? AND ResourceId = ? AND Deleted = 0",
                             [resource_type, resource_id], limit=1)
    if not rows or not rows[0][0]:
        raise HTTPException(404, "Zdroj nenalezen.")
    return json.loads(rows[0][0])


@router.get("/messages")
def messages(session: int | None = Query(None, ge=1)) -> list[dict]:
    with _connection() as connection:
        if session is None:
            _, rows, _ = _select(connection, f"SELECT TOP {MESSAGE_LIMIT} {MESSAGE_COLUMNS} FROM Ens.MessageHeader ORDER BY ID DESC")
        else:
            _, rows, _ = _select(connection, f"SELECT {MESSAGE_COLUMNS} FROM Ens.MessageHeader WHERE SessionId = ? ORDER BY ID", [session])
    return [_message(row) for row in rows]


@router.get("/messages/{message_id}")
def message(message_id: int) -> dict:
    with _connection() as connection:
        _, rows, _ = _select(connection, f"SELECT {MESSAGE_COLUMNS}, MessageBodyId FROM Ens.MessageHeader WHERE ID = ?", [message_id], limit=1)
        if not rows:
            raise HTTPException(404, "Zpráva nenalezena.")
        body_sql = MESSAGE_BODIES.get(rows[0][5])
        body_rows = _select(connection, body_sql, [rows[0][9]], limit=1)[1] if body_sql and rows[0][9] else []
    body = body_rows[0][0] if body_rows else None
    return {**_message(rows[0]), "body": body.replace("\r", "\n") if isinstance(body, str) else body}
