import argparse
import hashlib
import json
import math
import re
import threading

from app.adapters.meddi_json import doc_path, load_patients, load_questionnaires, dataset_dir
from app.agent.patient_guide import PATIENT_TEXTS
from app.config import settings

EMBED_DIR = settings.cache_dir / "embeddings"
CHUNKS_FILE = EMBED_DIR / "guide_chunks.json"

DDL = [
    "CREATE TABLE MEDDI.Guide_Chunk (Id INT, Source VARCHAR(200), \"Section\" VARCHAR(120), Lang VARCHAR(5), "
    "Audience VARCHAR(10), Txt VARCHAR(4000), Emb VECTOR(DOUBLE, 1536))",
    "CREATE INDEX GuideHNSW ON TABLE MEDDI.Guide_Chunk (Emb) AS HNSW(Distance='Cosine')",
    "CREATE TABLE MEDDI.Checkin_Text (CheckinId VARCHAR(20), PatientId VARCHAR(12), Scenario VARCHAR(12), "
    "Lang VARCHAR(5), Txt VARCHAR(4000), Emb VECTOR(DOUBLE, 1536))",
    "CREATE INDEX CheckinHNSW ON TABLE MEDDI.Checkin_Text (Emb) AS HNSW(Distance='Cosine')",
]

_lock = threading.Lock()
_connection = None
_client = None


def _openai():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=settings.openai_api_key, timeout=20)
    return _client


def _cache_path(text: str):
    digest = hashlib.sha256(f"{settings.embed_model}\n{text}".encode()).hexdigest()
    return EMBED_DIR / f"{digest}.json"


def embed(texts: list[str]) -> list[list[float]]:
    EMBED_DIR.mkdir(parents=True, exist_ok=True)
    missing = [text for text in dict.fromkeys(texts) if not _cache_path(text).exists()]
    for start in range(0, len(missing), 100):
        batch = missing[start : start + 100]
        response = _openai().embeddings.create(model=settings.embed_model, input=batch)
        for text, item in zip(batch, response.data):
            _cache_path(text).write_text(json.dumps(item.embedding), encoding="utf-8")
    return [json.loads(_cache_path(text).read_text(encoding="utf-8")) for text in texts]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().split(".", 1)[-1].strip()).strip("-")[:60] or "obecne"


def _markdown_chunks(text: str, source: str) -> list[dict]:
    chunks: list[dict] = []
    heading = ""
    paragraph: list[str] = []

    def flush():
        if paragraph:
            chunks.append({"source": source, "section": heading, "txt": f"{heading}: {' '.join(paragraph)}"})
            paragraph.clear()

    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            flush()
            heading = line.lstrip("#").strip()
        elif line.startswith("|"):
            flush()
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", cell) for cell in cells) or cells[0] in ("Úroveň", "Oblast", "Kontext", "ID", "Pole", "Dotazník", "Zadání: řešení…"):
                continue
            chunks.append({"source": source, "section": heading, "txt": f"{heading}: {' – '.join(cells)}"})
        elif re.match(r"^(-|\d+\.)\s", line):
            flush()
            chunks.append({"source": source, "section": heading, "txt": f"{heading}: {re.sub(r'^(-|\d+\.)\s+', '', line)}"})
        elif line and line != "---" and not line.startswith(">"):
            paragraph.append(line)
        else:
            flush()
    flush()
    return chunks


def guide_chunks() -> list[dict]:
    chunks: list[dict] = []
    for chunk in _markdown_chunks(doc_path("pravidla_triaze.md").read_text(encoding="utf-8"), "pravidla_triaze"):
        chunks.append({**chunk, "lang": "cs", "audience": "clinician"})
    readme = (dataset_dir("dev") / "README.md").read_text(encoding="utf-8")
    rules = readme.split("## 6. Povinná pravidla řešení", 1)[1]
    for chunk in _markdown_chunks("## Povinná pravidla řešení" + rules, "readme"):
        chunks.append({**chunk, "lang": "cs", "audience": "clinician"})
    seen: set[str] = set()
    for questionnaire in load_questionnaires():
        for question in questionnaire.get("otazky", []):
            for option in question.get("moznosti", []):
                warning = option.get("upozorneni")
                if warning and warning not in seen:
                    seen.add(warning)
                    chunks.append({"source": "dotazniky", "section": question["id"], "lang": "cs", "audience": "patient",
                                   "txt": f"{question['text']} {warning}"})
    for section, texts in PATIENT_TEXTS.items():
        for lang, text in texts.items():
            chunks.append({"source": "pacient", "section": section, "lang": lang, "audience": "patient", "txt": text})
    for number, chunk in enumerate(chunks, 1):
        chunk["id"] = number
        chunk["section"] = chunk["section"][:120]
        chunk["cite"] = f"guide:{chunk['source']}#{_slug(chunk['section']) if chunk['source'] != 'pacient' else chunk['section']}"
    return chunks


def checkin_texts() -> list[dict]:
    rows = []
    for patient in load_patients("dev"):
        for checkin in patient.checkiny:
            if checkin.zprava_pacienta and len(checkin.zprava_pacienta) > 12:
                rows.append({"checkin_id": checkin.checkin_id, "patient_id": patient.patient_id, "scenario": patient.patient_id,
                             "lang": patient.demografie.jazyk, "txt": checkin.zprava_pacienta[:4000]})
    return rows


def _connect():
    import iris

    return iris.connect(settings.iris_host, settings.iris_port, settings.iris_namespace, settings.iris_user,
                        settings.iris_password, timeout=5000)


def _query(sql: str, params: list) -> list:
    global _connection
    with _lock:
        for attempt in (1, 2):
            try:
                if _connection is None:
                    _connection = _connect()
                cursor = _connection.cursor()
                try:
                    cursor.execute(sql, params)
                    return cursor.fetchall()
                finally:
                    cursor.close()
            except Exception:
                try:
                    if _connection is not None:
                        _connection.close()
                except Exception:
                    pass
                _connection = None
                if attempt == 2:
                    raise
    return []


def build() -> None:
    chunks = guide_chunks()
    checkins = checkin_texts()
    guide_vectors = embed([chunk["txt"] for chunk in chunks])
    checkin_vectors = embed([row["txt"] for row in checkins])
    CHUNKS_FILE.write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    connection = _connect()
    try:
        cursor = connection.cursor()
        for table in ("MEDDI.Guide_Chunk", "MEDDI.Checkin_Text"):
            try:
                cursor.execute(f"DROP TABLE {table}")
            except Exception:
                pass
        for statement in DDL:
            cursor.execute(statement)
        cursor.executemany(
            "INSERT INTO MEDDI.Guide_Chunk (Id, Source, \"Section\", Lang, Audience, Txt, Emb) VALUES (?, ?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE))",
            [[chunk["id"], chunk["cite"], chunk["section"], chunk["lang"], chunk["audience"], chunk["txt"], str(vector)]
             for chunk, vector in zip(chunks, guide_vectors)],
        )
        cursor.executemany(
            "INSERT INTO MEDDI.Checkin_Text (CheckinId, PatientId, Scenario, Lang, Txt, Emb) VALUES (?, ?, ?, ?, ?, TO_VECTOR(?, DOUBLE))",
            [[row["checkin_id"], row["patient_id"], row["scenario"], row["lang"], row["txt"], str(vector)]
             for row, vector in zip(checkins, checkin_vectors)],
        )
        connection.commit()
        cursor.close()
    finally:
        connection.close()
    patient_count = sum(chunk["audience"] == "patient" for chunk in chunks)
    print(f"Guide_Chunk: {len(chunks)} rows ({patient_count} patient), Checkin_Text: {len(checkins)} rows")


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    return dot / (math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right)) or 1.0)


def _local_search(query_vector: list[float], lang: str, audience: str, k: int) -> list[dict]:
    # ponytail: fallback when IRIS is down, linear scan over the cached chunk embeddings
    chunks = [chunk for chunk in json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
              if chunk["audience"] == audience and chunk["lang"] == lang]
    vectors = embed([chunk["txt"] for chunk in chunks])
    scored = sorted(zip(chunks, vectors), key=lambda pair: _cosine(pair[1], query_vector), reverse=True)[:k]
    return [{"source": chunk["cite"], "section": chunk["section"], "text": chunk["txt"], "score": round(_cosine(vector, query_vector), 3),
             "engine": "local"} for chunk, vector in scored]


def search_guidance(query: str, lang: str = "cs", audience: str = "patient", k: int = 5) -> list[dict]:
    query_vector = embed([query])[0]
    try:
        rows = _query(
            f"SELECT TOP {int(k)} Source, \"Section\", Txt, VECTOR_COSINE(Emb, TO_VECTOR(?, DOUBLE)) AS Score FROM MEDDI.Guide_Chunk "
            "WHERE Audience = ? AND Lang = ? ORDER BY Score DESC",
            [str(query_vector), audience, lang],
        )
        return [{"source": source, "section": section, "text": text, "score": round(float(score), 3), "engine": "iris"}
                for source, section, text, score in rows]
    except Exception:
        if not CHUNKS_FILE.exists():
            return []
        return _local_search(query_vector, lang, audience, k)


def search_similar_checkins(query: str, exclude_patient_id: str, k: int = 3) -> list[dict]:
    query_vector = embed([query])[0]
    try:
        rows = _query(
            f"SELECT TOP {int(k)} CheckinId, Lang, Txt, VECTOR_COSINE(Emb, TO_VECTOR(?, DOUBLE)) AS Score FROM MEDDI.Checkin_Text "
            "WHERE PatientId <> ? AND Scenario <> ? ORDER BY Score DESC",
            [str(query_vector), exclude_patient_id, exclude_patient_id],
        )
    except Exception:
        return []
    return [{"checkin_id": checkin_id, "lang": lang, "text": text, "score": round(float(score), 3)}
            for checkin_id, lang, text, score in rows]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--search")
    parser.add_argument("--lang", default="cs")
    args = parser.parse_args()
    if args.build:
        build()
    if args.search:
        for hit in search_guidance(args.search, args.lang):
            print(hit["score"], hit["source"], hit["text"][:120])
