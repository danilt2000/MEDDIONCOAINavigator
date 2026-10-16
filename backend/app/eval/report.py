TARGETS = {
    "red_recall": ("≥", 100), "orange_recall": ("≥", 95), "under_triage_by_2": ("≤", 0), "under_triage": ("≤", 3),
    "false_alarms": ("≤", 15), "notify_agreement": ("≥", 95), "routing": ("≥", 95), "exact_level": ("≥", 85),
}


def table(name: str, result: dict) -> str:
    metrics = result["metrics"]
    lines = [f"== {name}: {metrics['checkins']} check-ins"]
    for key, value in metrics.items():
        if key == "checkins":
            continue
        target = TARGETS.get(key)
        ok = ""
        if target and value is not None:
            ok = "ok" if (value >= target[1] if target[0] == "≥" else value <= target[1]) else "MISS"
        lines.append(f"  {key:<20} {value!s:>7}  {(target[0] + str(target[1])) if target else '':>6}  {ok}")
    lines.append("  confusion (rows GT 1-4, cols predicted 1-4):")
    lines += [f"    GT{index + 1}: " + " ".join(f"{cell:>4}" for cell in row) for index, row in enumerate(result["confusion"])]
    return "\n".join(lines)
