import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import iris_explorer
from app.config import settings

WRITES = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|CALL|EXEC|EXECUTE|MERGE|SET|KILL)\b", re.I)


class FakeCursor:
    def __init__(self, database):
        self.database = database
        self.description = None
        self.rows = []

    def setQueryTimeout(self, seconds):
        self.database.timeouts.append(seconds)

    def execute(self, sql, params=None):
        self.database.executed.append((sql, params))
        columns, self.rows = self.database.answer(sql, params)
        self.description = [(column,) for column in columns]

    def fetchmany(self, size):
        return self.rows[:size]

    def close(self):
        pass


class FakeConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self):
        return FakeCursor(self.database)

    def close(self):
        self.database.closed += 1


@pytest.fixture
def iris(monkeypatch):
    database = SimpleNamespace(executed=[], timeouts=[], closed=0, answer=lambda sql, params: (["n"], [[1]]))
    monkeypatch.setattr(iris_explorer, "_open", lambda: FakeConnection(database))
    app = FastAPI()
    app.include_router(iris_explorer.router)
    database.client = TestClient(app)
    return database


def test_whitelist_is_read_only_and_has_the_demo_queries():
    sqls = {query["id"]: query["sql"] for query in iris_explorer.QUERIES}
    assert len(sqls) == len(iris_explorer.QUERIES)
    for sql in sqls.values():
        assert sql.lstrip().upper().startswith("SELECT")
        assert ";" not in sql and "?" not in sql
        assert not WRITES.search(sql), sql
    assert "SELECT TOP 20 ResourceType, Id, ResourceString FROM HSFHIR_X0001_R.Rsrc WHERE Deleted = 0" in sqls.values()
    assert any("MEDDI.Triage_Result t JOIN MEDDI.Triage_Rule r ON t.RuleIds [ r.RuleId" in sql for sql in sqls.values())


def test_unknown_query_is_404_without_touching_iris(iris):
    response = iris.client.post("/api/iris/queries/DROP TABLE MEDDI.Triage_Rule/run")
    assert response.status_code == 404
    assert iris.client.post("/api/iris/queries/nope/run").status_code == 404
    assert iris.executed == []


def test_run_executes_only_the_server_sql_and_caps_rows(iris):
    iris.answer = lambda sql, params: (["EffectiveAt", "kg"], [[f"2026-09-{index}", 80 + index] for index in range(500)])
    response = iris.client.post("/api/iris/queries/vaha-onc007/run")
    body = response.json()
    assert response.status_code == 200
    assert body["columns"] == ["EffectiveAt", "kg"]
    assert len(body["rows"]) == iris_explorer.ROW_LIMIT == 200
    assert body["truncated"] is True
    assert iris.executed == [(iris_explorer.QUERIES_BY_ID["vaha-onc007"]["sql"], None)]
    assert iris.timeouts == [iris_explorer.TIMEOUT_SECONDS]
    assert iris.closed == 1


def test_fhir_browser_validates_and_binds_the_resource_type(iris):
    for bad in ("Patient' OR 1=1 --", "patient", "Observation;DROP", "A"):
        assert iris.client.get("/api/iris/fhir", params={"type": bad}).status_code == 422
    assert iris.client.get("/api/iris/fhir/Patient/ONC-001'--").status_code == 422
    assert iris.executed == []

    iris.answer = lambda sql, params: (["n"], [[3]]) if "COUNT" in sql else (["id", "modified", "version"], [["ONC-001", "2026-10-17T02:00:00Z", 4]])
    body = iris.client.get("/api/iris/fhir", params={"type": "Patient", "page": 2}).json()
    assert body["total"] == 3 and body["items"] == [{"id": "ONC-001", "last_modified": "2026-10-17T02:00:00Z", "version": "4"}]
    assert all(params == ["Patient"] and "Patient" not in sql for sql, params in iris.executed)
    assert "OFFSET 100" in iris.executed[-1][0]

    iris.answer = lambda sql, params: (["ResourceString"], [['{"resourceType": "Patient", "id": "ONC-001"}']])
    assert iris.client.get("/api/iris/fhir/Patient/ONC-001").json() == {"resourceType": "Patient", "id": "ONC-001"}
    assert iris.executed[-1][1] == ["Patient", "ONC-001"]


def test_iris_down_is_a_clear_503(monkeypatch):
    monkeypatch.setattr(settings, "iris_port", 1999)
    app = FastAPI()
    app.include_router(iris_explorer.router)
    client = TestClient(app)
    responses = [client.get("/api/iris/overview")]

    def refuse():
        raise ConnectionRefusedError("localhost:1999")

    monkeypatch.setattr(iris_explorer, "_open", refuse)
    responses += [client.post("/api/iris/queries/vaha-onc007/run"), client.get("/api/iris/fhir", params={"type": "Patient"}),
                  client.get("/api/iris/fhir/Patient/ONC-001"), client.get("/api/iris/messages"), client.get("/api/iris/messages/1")]
    for response in responses:
        assert response.status_code == 503
        assert response.json() == {"detail": iris_explorer.IRIS_DOWN}
