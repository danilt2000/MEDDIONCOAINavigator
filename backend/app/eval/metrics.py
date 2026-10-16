"""§13 metrics: recall per level, under-/over-triage, notify agreement, routing by contact category."""
from app.models import GroundTruth, TriageOutput
from app.triage.router import contact_category


def _pct(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 1) if denominator else None


def evaluate(outputs: list[TriageOutput], expected: dict[str, GroundTruth]) -> dict:
    pairs = [(output, expected[output.checkin_id]) for output in outputs if output.checkin_id in expected]
    confusion = [[0] * 4 for _ in range(4)]
    errors = []
    for output, truth in pairs:
        confusion[truth.uroven - 1][output.uroven - 1] += 1
        wrong_level = output.uroven != truth.uroven
        wrong_contact = output.doporuceny_kontakt != truth.doporuceny_kontakt
        if wrong_level or wrong_contact or output.upozornit_tym != truth.upozornit_tym:
            errors.append({
                "checkin_id": output.checkin_id, "patient_id": output.patient_id, "expected": truth.uroven, "predicted": output.uroven,
                "expected_contact": truth.doporuceny_kontakt, "predicted_contact": output.doporuceny_kontakt,
                "rules": output.pravidla, "findings": output.klicove_nalezy, "expected_findings": truth.klicove_nalezy,
                "kind": "under" if output.uroven < truth.uroven else "over" if output.uroven > truth.uroven else "routing",
            })
    n = len(pairs)
    red = [(o, t) for o, t in pairs if t.uroven == 4]
    orange = [(o, t) for o, t in pairs if t.uroven == 3]
    green = [(o, t) for o, t in pairs if t.uroven == 1]
    metrics = {
        "checkins": n,
        "red_recall": _pct(sum(o.uroven == 4 for o, _ in red), len(red)),
        "orange_recall": _pct(sum(o.uroven >= 3 for o, _ in orange), len(orange)),
        "under_triage_by_2": sum(t.uroven - o.uroven >= 2 for o, t in pairs),
        "under_triage": _pct(sum(o.uroven < t.uroven for o, t in pairs), n),
        "false_alarms": _pct(sum(o.uroven >= 2 for o, _ in green), len(green)),
        "false_alarms_3plus": _pct(sum(o.uroven >= 3 for o, _ in green), len(green)),
        "notify_agreement": _pct(sum(o.upozornit_tym == t.upozornit_tym for o, t in pairs), n),
        "routing": _pct(sum(contact_category(o.doporuceny_kontakt) == contact_category(t.doporuceny_kontakt) for o, t in pairs), n),
        "routing_exact": _pct(sum(o.doporuceny_kontakt == t.doporuceny_kontakt for o, t in pairs), n),
        "exact_level": _pct(sum(o.uroven == t.uroven for o, t in pairs), n),
        "step_agreement": _pct(sum(o.doporuceny_krok == t.doporuceny_krok for o, t in pairs), n),
    }
    return {"metrics": metrics, "confusion": confusion, "errors": errors}
