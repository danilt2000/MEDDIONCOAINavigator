import logging
import threading
import time
from contextlib import contextmanager

import httpx

from app.config import settings

log = logging.getLogger(__name__)

FHIR_JSON = "application/fhir+json"
_client: httpx.Client | None = None
_client_lock = threading.Lock()
_available: tuple[float, bool] = (0.0, False)


class FhirError(RuntimeError):
    pass


def client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            # ponytail: one shared client keeps the CSP session cookie, so IRIS counts one licence unit
            _client = httpx.Client(
                base_url=settings.fhir_base.rstrip("/") + "/",
                auth=(settings.iris_user, settings.iris_password),
                headers={"Accept": FHIR_JSON, "Content-Type": FHIR_JSON},
                timeout=httpx.Timeout(60.0, connect=2.0),
            )
        return _client


def fhir_available(ttl_ok: float = 30.0, ttl_down: float = 10.0) -> bool:
    global _available
    if not settings.fhir_enabled:
        return False
    checked_at, ok = _available
    if time.monotonic() - checked_at < (ttl_ok if ok else ttl_down):
        return ok
    try:
        ok = client().get("Device", params={"_summary": "count"}, timeout=1.5).status_code == 200
    except httpx.HTTPError:
        ok = False
    _available = (time.monotonic(), ok)
    return ok


def request(method: str, path: str, **kwargs) -> dict:
    response = client().request(method, path, **kwargs)
    if response.status_code >= 400:
        raise FhirError(f"{method} {path} -> {response.status_code}: {response.text[:800]}")
    return response.json() if response.content else {}


def get(path: str, params: dict | None = None) -> dict | None:
    response = client().get(path, params=params)
    if response.status_code in (404, 410):
        return None
    if response.status_code >= 400:
        raise FhirError(f"GET {path} -> {response.status_code}: {response.text[:800]}")
    return response.json()


def search(resource_type: str, params: dict) -> list[dict]:
    resources: list[dict] = []
    bundle = request("GET", resource_type, params=params)
    while True:
        resources += [entry["resource"] for entry in bundle.get("entry", []) if "resource" in entry]
        next_url = next((link["url"] for link in bundle.get("link", []) if link["relation"] == "next"), None)
        if not next_url:
            return resources
        bundle = request("GET", next_url)


def count(resource_type: str, params: dict | None = None) -> int:
    return request("GET", resource_type, params={**(params or {}), "_summary": "count"}).get("total", 0)


def compact(value):
    """FHIR JSON forbids null, empty arrays and empty objects."""
    if isinstance(value, dict):
        cleaned = {key: compact(item) for key, item in value.items()}
        return {key: item for key, item in cleaned.items() if item not in (None, [], {}, "")}
    if isinstance(value, list):
        return [item for item in (compact(item) for item in value) if item not in (None, [], {}, "")]
    return value


def put_entry(resource: dict) -> dict:
    resource = compact(resource)
    return {
        "fullUrl": f"{settings.fhir_base.rstrip('/')}/{resource['resourceType']}/{resource['id']}",
        "resource": resource,
        "request": {"method": "PUT", "url": f"{resource['resourceType']}/{resource['id']}"},
    }


def transaction(resources: list[dict], bundle_type: str = "transaction") -> dict:
    bundle = {"resourceType": "Bundle", "type": bundle_type, "entry": [put_entry(resource) for resource in resources]}
    return request("POST", "", json=bundle)


@contextmanager
def sql_connection():
    """One IRIS DB-API connection (Community Edition: keep at most 2 per process, always close)."""
    import iris

    connection = iris.connect(settings.iris_host, settings.iris_port, settings.iris_namespace,
                              settings.iris_user, settings.iris_password)
    try:
        yield connection
    finally:
        connection.close()


def tagged_keys(system: str, value: str) -> list[str]:
    """'Type/id' of every live resource with this meta.tag; FHIR search cannot list more than 1000 matches."""
    with sql_connection() as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT DISTINCT Key FROM HSFHIR_X0001_S_Rsrc._tag WHERE value_System = ? AND value_Value = ?",
                       [system, value])
        return [row[0] for row in cursor.fetchall()]


def delete_entries(references: list[str]) -> dict:
    bundle = {
        "resourceType": "Bundle",
        "type": "batch",
        "entry": [{"request": {"method": "DELETE", "url": reference}} for reference in references],
    }
    return request("POST", "", json=bundle)
