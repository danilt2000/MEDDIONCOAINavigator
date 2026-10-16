"""Create and load the MEDDI.* engine tables in IRIS SQL (spec §7).

    python -m app.fhir.sql_tables

Triage_Rule <- backend/app/triage/rules.yaml (when present), Drug_Class <- drug names found in the data,
Eval_Expected <- ground_truth/ (read only by app.eval). Triage_Result is filled by app.fhir.writers, Eval_Run by app.eval.
"""

import yaml

from app.adapters.meddi_json import DATASET_DIRS, load_ground_truth, load_patients
from app.config import REPO_ROOT
from app.fhir.client import sql_connection
from app.fhir.mappers import DRUG_CLASSES, REGIMENS, ascii_fold

DDL_PATH = REPO_ROOT / "iris" / "sql" / "meddi_tables.sql"
RULES_PATH = REPO_ROOT / "backend" / "app" / "triage" / "rules.yaml"


def ddl_statements() -> list[str]:
    lines = [line for line in DDL_PATH.read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def rule_rows() -> list[tuple]:
    if not RULES_PATH.exists():
        return []
    data = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8")) or []
    rules = data.get("rules", data) if isinstance(data, dict) else data
    if isinstance(rules, dict):
        rules = [{"id": rule_id, **(body or {})} for rule_id, body in rules.items()]
    rows = []
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("id"):
            continue
        expr = rule.get("label") or rule.get("expr") or rule.get("signals") or rule.get("description") or ""
        hint = rule.get("hint_cs") or rule.get("patient_hint") or rule.get("hint") or ""
        rows.append((
            str(rule["id"])[:30],
            int(rule.get("min_level") or rule.get("level") or 0),
            str(rule.get("area") or "")[:40],
            (", ".join(map(str, expr)) if isinstance(expr, list) else str(expr))[:500],
            str(hint)[:300],
            str(rule.get("source") or "")[:120],
            1 if rule.get("active", True) else 0,
        ))
    return rows


def drug_class_rows() -> list[tuple]:
    texts = []
    for dataset in DATASET_DIRS:
        for patient in load_patients(dataset):
            texts += [med.lek for med in patient.leky] + patient.lecba.leky + [patient.lecba.rezim]
    folded = ascii_fold(" ".join(texts)).lower()
    folded += " " + " ".join(drugs for acronym, drugs in REGIMENS.items() if acronym in folded)
    return sorted({(stem, name) for name, stems in DRUG_CLASSES.items() for stem in stems if stem in folded})


def eval_rows() -> list[tuple]:
    return [(item.checkin_id, dataset, item.uroven, item.doporuceny_krok, 1 if item.upozornit_tym else 0,
             item.doporuceny_kontakt) for dataset in DATASET_DIRS for item in load_ground_truth(dataset).values()]


def load_tables() -> dict[str, int]:
    loads = {
        "MEDDI.Triage_Rule": ("RuleId, MinLevel, Area, Expr, PatientHint, Source, Active", rule_rows()),
        "MEDDI.Drug_Class": ("Drug, Class", drug_class_rows()),
        "MEDDI.Eval_Expected": ("CheckinId, Dataset, TriageLevel, Step, NotifyTeam, Contact", eval_rows()),
    }
    counts = {}
    with sql_connection() as connection:
        cursor = connection.cursor()
        for statement in ddl_statements():
            cursor.execute(statement)
        for table, (columns, rows) in loads.items():
            cursor.execute(f"DELETE FROM {table}")
            if rows:
                placeholders = ", ".join("?" * len(rows[0]))
                cursor.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rows)
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        cursor.close()
    print("SQL " + ", ".join(f"{table} {total}" for table, total in counts.items()))
    return counts


if __name__ == "__main__":
    load_tables()
