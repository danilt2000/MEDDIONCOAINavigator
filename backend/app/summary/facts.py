import re
from datetime import date, datetime, timedelta

from app.models import PRAGUE, Checkin, Patient, PatientContext, SummaryFact, TriageOutput
from app.triage.validator import normalize

WINDOW = timedelta(days=14)

LEVEL_NAMES = {1: "zelená", 2: "žlutá", 3: "oranžová", 4: "červená"}
LEVEL_LINES = {
    1: "ZELENÁ – další sledování",
    2: "ŽLUTÁ – kontakt týmu",
    3: "ORANŽOVÁ – telekonzultace dnes",
    4: "ČERVENÁ – neodkladná pomoc",
}
REASONS = {
    "eskalace": "souhrn při eskalaci", "escalation": "souhrn při eskalaci",
    "aplikace": "souhrn před aplikací", "pred_aplikaci": "souhrn před aplikací", "application": "souhrn před aplikací",
    "tydenni": "týdenní souhrn", "weekly": "týdenní souhrn",
}
LAB_NAMES = {
    "leu": "leukocyty", "neu": "neutrofily", "hb": "Hb", "plt": "PLT", "kreat": "kreatinin", "na": "Na", "k": "K",
    "alt": "ALT", "bili": "bilirubin", "crp": "CRP", "tsh": "TSH", "ft4": "fT4", "mg": "Mg", "inr": "INR",
    "alb": "albumin", "psa": "PSA", "testo": "testosteron", "glu": "glukóza", "moc_bilk": "bílkovina v moči",
    "ntprobnp": "NT-proBNP",
}
SYMPTOMS: dict[str, tuple[str, list[str]]] = {
    "prujem": ("průjem", ["≤ 3 stolice navíc", "4–6 stolic navíc", "≥ 7 stolic navíc", "nezvladatelný"]),
    "zvraceni": ("zvracení", ["1–2×/24 h", "3–5×/24 h", "> 5×/24 h", "nezvladatelné"]),
    "dusnost": ("dušnost", ["bez omezení", "lehce omezuje", "při běžných činnostech", "v klidu"]),
    "teplota": ("teplota", ["37,0–37,9 °C", "38,0–39,0 °C", "39,0–40,0 °C", "> 40 °C", "> 40 °C déle než 24 h"]),
    "nevolnost": ("nevolnost", ["neomezuje příjem", "mírně omezuje příjem", "příjem na minimu", "příjem na minimu, doma nezvládá"]),
    "nechutenstvi": ("nechutenství", ["neomezuje", "jí méně", "hubne", "příjem na minimu"]),
    "afty": ("afty/polykání", ["neomezují", "mění příjem", "jen tekutá strava", "nezvladatelné"]),
    "zacpa": ("zácpa", ["občasná", "trvá, mírně omezuje", "velmi omezuje", "nezvladatelná"]),
    "bol_hlava": ("bolest hlavy", ["mírná", "s léky", "silná, omezuje"]),
    "bol_hrud": ("bolest na hrudi", ["dlouhodobá", "nová"]),
    "bol_bricho": ("bolest břicha", ["mírná", "střední", "silná"]),
    "bol_klouby": ("bolest kloubů", ["mírná", "střední", "silná"]),
    "brneni": ("brnění", ["mírné", "omezuje činnosti", "omezuje soběstačnost"]),
    "kuze": ("kůže", ["minimální změny", "bolestivé, omezuje", "omezuje soběstačnost"]),
    "unava": ("únava", ["ustoupí odpočinkem", "omezuje náročné aktivity", "omezuje běžné činnosti"]),
    "krvaceni": ("krvácení", ["ne", "ano"]),
    "moceni": ("potíže s močením", ["ne", "ano"]),
}
RED_FLAGS = [
    (5, "horečku", ("teplot", "horec", "horuc", "zimnic", "tresavk", "triask")),
    (10, "dušnost", ("dusn", "dych", "polstar", "ortopno")),
    (8, "krvácení", ("krv", "krev", "modrin", "hematom")),
    (3, "bolest na hrudi", ("hrud",)),
]
VITALS = [
    ("vaha_kg", "váha", "{} kg", 1, lambda values: len(values) >= 2 and abs(values[-1] - values[0]) >= 1.0),
    ("teplota_c", "teplota", "{} °C", 1, lambda values: max(values) >= 37.5),
    ("tepova_frekvence", "tep", "{}", None, lambda values: max(values) >= 100 or values[-1] - min(values) >= 15),
    ("glykemie_mmol_l", "glykémie", "{} mmol/l", 1, lambda values: max(values) > 10 or min(values) < 4),
    ("spo2", "SpO2", "{} %", None, lambda values: min(values) < 94),
    ("dechova_frekvence", "dech", "{}/min", None, lambda values: min(values) <= 10 or max(values) >= 22),
]
TIMING = {1: "při příštím kontaktu", 2: "do konce následujícího pracovního dne", 3: "dnes", 4: "okamžitě"}
CYCLE_MARK = re.compile(r"\bC\d+ D\d+\b")
NO_SIDE_EFFECTS = 12
CHEST_PAIN_OPTION = 1


def aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=PRAGUE)


def day_month(day: date) -> str:
    return f"{day.day}. {day.month}."


def number(value: float, decimals: int | None = None) -> str:
    text = f"{value:.{decimals}f}" if decimals is not None else f"{value:g}"
    return text.replace(".", ",")


def shorten(text: str, words: int = 12) -> str:
    parts = text.split()
    return text if len(parts) <= words else " ".join(parts[:words]).rstrip(",;:.") + " …"


def series(points: list[tuple[date, str]], limit: int = 3) -> str:
    if len(points) > limit:
        points = points[:1] + points[-(limit - 1):]
    if len({value for _, value in points}) == 1:
        return f"{points[0][1]} od {day_month(points[0][0])}"
    return " → ".join(f"{day_month(day)} {value}" for day, value in points)


def author_label(vyplnil: str) -> str:
    return "pacient" if vyplnil == "pacient" else vyplnil


def visible_outputs(outputs: list[TriageOutput], patient_id: str, as_of: datetime) -> list[TriageOutput]:
    kept = [output for output in outputs if output.patient_id == patient_id and aware(output.as_of) <= as_of]
    return sorted(kept, key=lambda output: aware(output.as_of))


def window_checkins(ctx: PatientContext, as_of: datetime) -> list[Checkin]:
    kept = [checkin for checkin in ctx.recent_checkins if as_of - WINDOW <= checkin.timestamp <= as_of]
    return sorted(kept, key=lambda checkin: checkin.timestamp)


def current_cycle(patient: Patient, ctx: PatientContext, as_of: datetime) -> tuple[int | None, int | None]:
    if ctx.cycle is not None:
        return ctx.cycle, ctx.cycle_day
    started = [cycle for cycle in patient.lecba.cykly if cycle.datum_d1 <= as_of.date()]
    if not started:
        return None, None
    last = max(started, key=lambda cycle: cycle.datum_d1)
    return last.cyklus, (as_of.date() - last.datum_d1).days + 1


def header(patient: Patient, as_of: datetime, reason: str, cycle: int | None) -> str:
    label = REASONS.get(normalize(reason or ""), "souhrn na vyžádání")
    if label == "souhrn před aplikací" and cycle:
        label += f" C{cycle}"
    demo = patient.demografie
    return f"{patient.patient_id} · {demo.jmeno_fiktivni}, {demo.vek} let · {label} ({as_of:%Y-%m-%d, %H:%M})"


def _answers(checkin: Checkin) -> dict[str, object]:
    return {
        answer.otazka_id: answer.odpoved_index
        for fill in checkin.dotazniky
        if fill.dotaznik_id == "nezadouci_ucinky"
        for answer in fill.odpovedi
    }


def specific_findings(latest: TriageOutput | None, ctx: PatientContext) -> list[str]:
    """The engine's findings without the context lines it appends (regimen and cycle, risk drugs, caregiver, directive)."""
    if latest is None:
        return []
    regimen = normalize(ctx.regimen)
    return [
        finding for finding in latest.klicove_nalezy
        if not CYCLE_MARK.search(finding)
        and not normalize(finding).startswith(("rizikove leky", "vyplnuje", "drive vyslovene prani"))
        and not (regimen and regimen.startswith(normalize(finding).strip()))
    ]


def proc_ted(latest: TriageOutput | None, ctx: PatientContext, checkins: list[Checkin]) -> list[SummaryFact]:
    if latest is None:
        last = checkins[-1] if checkins else None
        text = f"bez eskalace, poslední záznam {day_month(last.datum)}" if last else "bez záznamů za posledních 14 dní"
        return [SummaryFact(text=text, datum=last.datum.isoformat() if last else None, zdroj="záznam")]
    day = aware(latest.as_of).date().isoformat()
    facts = []
    findings = specific_findings(latest, ctx)
    if findings:
        facts.append(SummaryFact(text="; ".join(findings[:3]), datum=day, zdroj="záznam", ref=latest.checkin_id))
    facts.append(
        SummaryFact(text=f"Úroveň {LEVEL_LINES[latest.uroven]} (odhad systému)", datum=day, zdroj="odhad systému", ref=latest.checkin_id)
    )
    return facts


def lecba(patient: Patient, ctx: PatientContext, cycle: int | None, cycle_day: int | None, checkins: list[Checkin], as_of: datetime) -> list[SummaryFact]:
    regimen = ctx.regimen or patient.lecba.rezim
    if cycle:
        regimen += f"; C{cycle}" + (f" D{cycle_day}" if cycle_day else "")
    facts = [SummaryFact(text=regimen, zdroj="záznam")]
    if ctx.advance_directive:
        facts.append(SummaryFact(text=f"DVP: {shorten(ctx.advance_directive, 10)}", zdroj="záznam"))
    caregivers = {checkin.vyplnil for checkin in checkins if checkin.vyplnil != "pacient"}
    if caregivers:
        facts.append(SummaryFact(text=f"vyplňuje {', '.join(sorted(caregivers))}", zdroj="záznam"))
    exams = [exam for exam in ctx.exams if exam.datum < as_of.date()]
    if exams:
        exam = max(exams, key=lambda item: item.datum)
        facts.append(
            SummaryFact(text=f"{exam.vysetreni} {day_month(exam.datum)}: {shorten(exam.vysledek, 8)}", datum=exam.datum.isoformat(), zdroj="naměřeno")
        )
    if ctx.comorbidities:
        facts.append(SummaryFact(text=f"komorbidity: {', '.join(ctx.comorbidities[:2])}", zdroj="záznam"))
    return facts


def _measured(label: str, points: list[tuple[date, str]], source: str = "naměřeno") -> SummaryFact:
    return SummaryFact(text=f"{label} {series(points)} ({source})", datum=points[-1][0].isoformat(), zdroj=source)


def _vital_series(checkins: list[Checkin]) -> list[SummaryFact]:
    measured = [checkin for checkin in checkins if checkin.vitalni_funkce]
    facts = []
    pressure = [
        (checkin.datum, checkin.vitalni_funkce["tk_sys"].hodnota, checkin.vitalni_funkce["tk_dia"].hodnota)
        for checkin in measured
        if "tk_sys" in checkin.vitalni_funkce and "tk_dia" in checkin.vitalni_funkce
    ]
    if any(systolic >= 140 or diastolic >= 90 or systolic < 100 for _, systolic, diastolic in pressure):
        facts.append(_measured("TK", [(day, f"{number(systolic)}/{number(diastolic)}") for day, systolic, diastolic in pressure]))
    for key, label, unit, decimals, show in VITALS:
        points = [(checkin.datum, checkin.vitalni_funkce[key].hodnota) for checkin in measured if key in checkin.vitalni_funkce]
        if points and show([value for _, value in points]):
            facts.append(_measured(label, [(day, unit.format(number(value, decimals))) for day, value in points]))
    return facts


def _symptom_series(checkins: list[Checkin], skip: set[str]) -> list[SummaryFact]:
    answered = [(checkin.datum, _answers(checkin)) for checkin in checkins]
    facts = []
    for otazka_id, (label, options) in SYMPTOMS.items():
        if label in skip:
            continue
        points = [
            (day, answers[otazka_id])
            for day, answers in answered
            if isinstance(answers.get(otazka_id), int) and 0 <= answers[otazka_id] < len(options)
        ]
        if points and (otazka_id == "teplota" or max(index for _, index in points) >= 1):
            facts.append(_measured(label, [(day, options[index]) for day, index in points], "pacient"))
    return facts


def _quotes(latest: TriageOutput | None, checkins: list[Checkin]) -> list[SummaryFact]:
    author = author_label(checkins[-1].vyplnil) if checkins else "pacient"
    if latest:
        quotes = [
            evidence for evidence in latest.dukazy
            if any(source in normalize(evidence.zdroj) for source in ("zprav", "chat", "prilo")) and evidence.citace
        ][:1]
        if quotes:
            day = aware(latest.as_of).date()
            return [
                SummaryFact(text=f"{day_month(day)} „{shorten(evidence.citace)}“ ({author})", datum=day.isoformat(), zdroj=author, ref=evidence.checkin_id)
                for evidence in quotes
            ]
    with_message = [checkin for checkin in checkins if checkin.zprava_pacienta]
    if not with_message:
        return []
    last = with_message[-1]
    return [
        SummaryFact(
            text=f"{day_month(last.datum)} „{shorten(last.zprava_pacienta)}“ ({author_label(last.vyplnil)})",
            datum=last.datum.isoformat(),
            zdroj=author_label(last.vyplnil),
            ref=last.checkin_id,
        )
    ]


def vyvoj(ctx: PatientContext, outputs: list[TriageOutput], latest: TriageOutput | None, checkins: list[Checkin], as_of: datetime) -> list[SummaryFact]:
    filled = [checkin for checkin in checkins if checkin.stav == "vyplneno"]
    vitals = _vital_series(filled)
    measured_labels = {fact.text.split()[0] for fact in vitals}
    facts = _quotes(latest, filled) + vitals + _symptom_series(filled, measured_labels)
    feeling = [(checkin.datum, _answers(checkin).get("pocit")) for checkin in filled]
    feeling = [(day, index) for day, index in feeling if isinstance(index, int)]
    missed = [checkin for checkin in checkins if checkin.stav == "nevyplneno"]
    if missed:
        facts.append(
            SummaryFact(text=f"nevyplněno: {', '.join(day_month(checkin.datum) for checkin in missed[-3:])}", datum=missed[-1].datum.isoformat(), zdroj="záznam")
        )
    events = [event for event in ctx.team_events if as_of - WINDOW <= event.timestamp <= as_of]
    if events:
        event = max(events, key=lambda item: item.timestamp)
        facts.append(
            SummaryFact(text=f"{day_month(event.datum)} {event.typ}: {shorten(event.text, 10)} (tým)", datum=event.datum.isoformat(), zdroj="tým")
        )
    if feeling and max(index for _, index in feeling) >= 3:
        facts.append(_measured("celkový stav (1–5)", [(day, str(index + 1)) for day, index in feeling], "pacient"))
    recent = [output for output in outputs if aware(output.as_of) >= as_of - WINDOW][-4:]
    if len(recent) >= 2 and max(output.uroven for output in recent) >= 2:
        levels = " → ".join(f"{day_month(aware(output.as_of).date())} {LEVEL_NAMES[output.uroven]}" for output in recent)
        facts.append(SummaryFact(text=f"úroveň {levels} (odhad systému)", datum=aware(recent[-1].as_of).date().isoformat(), zdroj="odhad systému"))
    return facts


def laborator(ctx: PatientContext, as_of: datetime) -> tuple[str | None, list[SummaryFact]]:
    labs = [lab for lab in ctx.labs if lab.timestamp <= as_of]
    if not labs:
        return None, []
    last_day = max(lab.datum for lab in labs)
    latest = [lab for lab in labs if lab.datum == last_day]
    abnormal = [lab for lab in latest if lab.priznak in ("L", "H")]
    if not abnormal:
        if as_of.date() - last_day > WINDOW:
            return None, []
        return day_month(last_day), [SummaryFact(text="bez odchylek (naměřeno)", datum=last_day.isoformat(), zdroj="naměřeno")]
    facts = []
    for lab in abnormal:
        history = sorted((item for item in labs if item.kod == lab.kod and last_day - item.datum <= timedelta(days=30)), key=lambda item: item.timestamp)
        values = " → ".join(number(item.hodnota) for item in history[-3:])
        name = LAB_NAMES.get(lab.kod, lab.test)
        facts.append(SummaryFact(text=f"{name} {values} {lab.jednotka} {lab.priznak} (naměřeno)", datum=last_day.isoformat(), zdroj="naměřeno", ref=lab.odber_id))
    return day_month(last_day), facts


def nehlasi(latest: TriageOutput | None, checkins: list[Checkin], as_of: datetime) -> list[SummaryFact]:
    filled = [checkin for checkin in checkins if checkin.stav == "vyplneno" and _answers(checkin).get("ucinky") is not None]
    if not filled:
        return []
    last = filled[-1]
    answers = _answers(last)
    selected = answers["ucinky"] if isinstance(answers["ucinky"], list) else [answers["ucinky"]]
    reported_text = normalize(" ".join([
        last.zprava_pacienta or "", *last.prilohy,
        *(latest.klicove_nalezy + latest.varovne_priznaky + [evidence.citace for evidence in latest.dukazy] if latest else []),
    ]))
    source = author_label(last.vyplnil) if last.datum == as_of.date() else f"{author_label(last.vyplnil)}, {day_month(last.datum)}"
    if NO_SIDE_EFFECTS in selected and not reported_text.strip():
        return [SummaryFact(text=f"žádné nežádoucí účinky ({source})", datum=last.datum.isoformat(), zdroj="pacient", ref=last.checkin_id)]
    chest_pain = answers.get("bolesti_typ")
    chest_pain_reported = 3 in selected and (not isinstance(chest_pain, list) or CHEST_PAIN_OPTION in chest_pain)
    missing = [
        label for option, label, stems in RED_FLAGS
        if option not in selected and not any(stem in reported_text for stem in stems) and not (option == 3 and chest_pain_reported)
    ]
    if not missing:
        return []
    return [SummaryFact(text=f"{', '.join(missing)} ({source})", datum=last.datum.isoformat(), zdroj="pacient", ref=last.checkin_id)]


def k_posouzeni(latest: TriageOutput | None, ctx: PatientContext, reason: str, cycle: int | None) -> list[SummaryFact]:
    if REASONS.get(normalize(reason or "")) == "souhrn před aplikací":
        timing = f"před dnešní aplikací{f' C{cycle}' if cycle else ''}"
    else:
        timing = TIMING[latest.uroven] if latest else "při příštím kontaktu"
    core = [shorten(re.split(r" \(| – |; ", finding)[0], 6) for finding in specific_findings(latest, ctx)[:2]]
    text = f"{timing} – {', '.join(core)}" if core else f"{timing} – průběh od posledního kontaktu"
    return [SummaryFact(text=text, zdroj="odhad systému", ref=latest.checkin_id if latest else None)]
