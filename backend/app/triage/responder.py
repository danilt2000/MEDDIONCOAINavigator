import logging
import re
from functools import cache
from pathlib import Path

import yaml

from app.models import Lek
from app.triage.validator import DOSE, normalize, validate_patient_text

log = logging.getLogger(__name__)

TOPICS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("psych", ("R-SUICIDE", "O-PSYCH", "Y-PSYCH"), ("sebevra", "smrt", "beznad", "zivot", "psycholog", "uzkost", "depres")),
    ("fever", ("R-FEVER",), ("teplot", "horec", "horuc", "zimnic", "tresavk", "triask")),
    ("bleeding", ("R-BLEED", "O-BLEED-ANTICOAG"), ("krvac", "krev", "krv ", "modrin", "hematom")),
    ("breath", ("R-BREATH", "R-CHEST", "O-BREATH", "T-SPO2"), ("dusn", "dych", "hrud", "ortopno", "polstar", "spo2")),
    ("opioid", ("R-OPIOID",), ("opioid", "spavost", "somnolen", "bradypno", "nereaguje")),
    ("diarrhea", ("R-DIARRHEA", "O-DIARRHEA-RISK", "O-IO-DIARRHEA-PAIN", "Y-IO-DIARRHEA"), ("prujem", "stolic", "hnack")),
    ("vomit", ("R-VOMIT", "O-VOMIT", "Y-VOMIT", "O-INTAKE", "R-DEHYD", "T-INTAKE"), ("zvrac", "tekutin", "mocen", "oligur", "anuri")),
    ("ileus", ("R-ILEUS",), ("zacp", "plyn")),
    ("bp", ("R-BP", "O-BP-ANTIANGIO", "Y-BP", "T-BP"), ("tlak", "tk ", "tk ", "hypertenz", "hypotenz")),
    ("glucose", ("O-HYPO", "Y-GLUCOSE", "R-DKA"), ("glyk", "cukr")),
    ("port", (), ("port ", "portu", "katetr")),
    ("neuro", ("R-NEURO",), ("zmaten", "vedomi", "kfec", "porucha reci")),
    ("pain", ("O-PAIN", "Y-PAIN"), ("bolest", "nrs", "sos")),
    ("caregiver", ("Y-CAREGIVER",), ("vycerp", "pecujic")),
]
IO_RULES = ("Y-IO-DIARRHEA", "O-IO-DIARRHEA-PAIN")
ANTICOAGULANTS = ("warfarin", "heparin", "enoxaparin", "nadroparin", "rivaroxaban", "apixaban", "dabigatran", "edoxaban")
SECOND_PERSON = re.compile(r"\b\w{3,}(?:íte|ete|áte|ate|ěte)\b")
OPIOIDS = ("morfin", "oramorph", "oxykodon", "fentanyl", "tramadol", "hydromorfon", "tapentadol")

WATCH = {
    "cs": {
        "fever": "teplota 38 °C a víc nebo zimnice",
        "bleeding": "černá stolice, krev v moči, krvácení z nosu déle než 20 minut nebo úraz hlavy",
        "breath": "dušnost v klidu, bolest na hrudi nebo pocit na omdlení",
        "opioid": "zmatenost, výrazná spavost nebo zpomalené dýchání",
        "diarrhea": "krev ve stolici, horečka, závratě nebo zástava močení",
        "vomit": "zvracení víc než 5× za den, zástava močení, zmatenost nebo pocit na omdlení",
        "ileus": "zástava plynů, zvracení nebo tvrdé bolestivé břicho",
        "bp": "tlak nad 180/110, silná bolest hlavy, porucha řeči nebo zraku či bolest na hrudi",
        "glucose": "zvracení, bolest břicha, zrychlené dýchání nebo zmatenost",
        "port": "šíření zarudnutí, hnis nebo teplota 38 °C a víc",
        "neuro": "zmatenost, porucha řeči nebo slabost končetin",
        "pain": "silná bolest, která nepovolí ani po léku podle rozpisu",
        "default": "teplota 38 °C a víc, dušnost, krvácení nebo jiné náhlé zhoršení",
    },
    "sk": {
        "fever": "teplota 38 °C a viac alebo zimnica",
        "bleeding": "čierna stolica, krv v moči, krvácanie z nosa dlhšie ako 20 minút alebo úraz hlavy",
        "breath": "dýchavičnosť v pokoji, bolesť na hrudi alebo pocit na odpadnutie",
        "opioid": "zmätenosť, výrazná spavosť alebo spomalené dýchanie",
        "diarrhea": "krv v stolici, horúčka, závraty alebo zástava močenia",
        "vomit": "vracanie viac ako 5× za deň, zástava močenia, zmätenosť alebo pocit na odpadnutie",
        "ileus": "zástava plynov, vracanie alebo tvrdé bolestivé brucho",
        "bp": "tlak nad 180/110, silná bolesť hlavy, porucha reči alebo zraku či bolesť na hrudi",
        "glucose": "vracanie, bolesť brucha, zrýchlené dýchanie alebo zmätenosť",
        "port": "šírenie začervenania, hnis alebo teplota 38 °C a viac",
        "neuro": "zmätenosť, porucha reči alebo slabosť končatín",
        "pain": "silná bolesť, ktorá nepovolí ani po lieku podľa rozpisu",
        "default": "teplota 38 °C a viac, dýchavičnosť, krvácanie alebo iné náhle zhoršenie",
    },
}

T = {
    "cs": {
        "l1_main": "Děkujeme, dnešní záznam je v očekávaném rozmezí.",
        "l1_main_cg": "Děkujeme, dnešní záznam {gen} je v očekávaném rozmezí.",
        "l1_continue": "Pokračujte podle doporučení.",
        "l1_earlier": "Ozvěte se dřív, pokud se {at}objeví {watch}.",
        "gap_l1": "Dnešní záznam chybí, vyplňte ho prosím, až to půjde.",
        "gap_l1_earlier": "Pokud se necítíte dobře, ozvěte se dřív.",
        "l2_main": "Váš záznam jsme předali týmu monitorovacího centra, ozve se vám {when}.",
        "l2_main_cg": "Záznam {gen} jsme předali týmu monitorovacího centra, ozve se vám {when}.",
        "gap_l2": "Několik dní nám chybí váš záznam, proto se vám ozve monitorovací centrum {when}.",
        "when_next_day_end": "nejpozději do konce následujícího pracovního dne",
        "when_next_day": "následující pracovní den",
        "l2_l3_watch": "Pokud se {at}objeví {watch}, volejte ihned 155.",
        "l1_earlier_hint": "Ozvěte se dřív, pokud: {watch}.",
        "l2_l3_watch_hint": "Volejte ihned 155, pokud: {watch}.",
        "l3_main": "Vaše potíže je potřeba ještě dnes probrat s lékařem MOÚ, ozve se vám do 2 hodin.",
        "l3_main_cg": "Potíže {gen} je potřeba ještě dnes probrat s lékařem MOÚ, ozve se vám do 2 hodin.",
        "l3_main_ooh": "Vaše potíže je potřeba ještě dnes probrat s lékařem, volejte ihned sloužícího lékaře MOÚ 724 590 848.",
        "l3_main_ooh_cg": "Potíže {gen} je potřeba ještě dnes probrat s lékařem, volejte ihned sloužícího lékaře MOÚ 724 590 848.",
        "meanwhile": "Do té doby {action}.",
        "l4_ems": "Volejte ihned 155 nebo jeďte na urgentní příjem.",
        "l4_on_duty": "Volejte ihned 155 nebo sloužícího lékaře MOÚ 724 590 848.",
        "l4_wait_night": "Nečekejte do rána.",
        "l4_wait_day": "Nečekejte, až to přejde.",
        "l4_wait_night_cg": "Stav {gen} je potřeba posoudit okamžitě, nečekejte do rána.",
        "l4_wait_day_cg": "Stav {gen} je potřeba posoudit okamžitě, nečekejte.",
        "med_list": "Vezměte si s sebou seznam léků.",
        "paralen": "Paralen neužívejte, dokud vás nevyšetří lékař.",
        "paralen_cg": "Paralen nepodávejte, dokud {acc}nevyšetří lékař.",
        "opioid_stop": "Další dávky léků na bolest teď neužívejte.",
        "opioid_stop_cg": "Další dávky léků na bolest teď nepodávejte.",
        "port": "Na port nesahejte.",
        "palliative": "Můžete volat i 24hodinovou linku paliativního týmu.",
        "psych": "Pokud by se objevily myšlenky ublížit si, volejte ihned 155 nebo Linku první psychické pomoci 116 123 (nonstop).",
        "caregiver": "Péče je náročná a je v pořádku říct si o pomoc.",
        "anticoag": "Dávkování léků na ředění krve neměňte bez pokynu lékaře.",
        "bp_l2": "Tlak si dál měřte ráno a večer.",
        "bp_l3": "Za hodinu si tlak změřte znovu v klidu.",
        "pain_l3": "neužívejte další dávky nad rámec rozpisu",
        "pain_l3_cg": "nepodávejte další dávky nad rámec rozpisu",
        "take": "užívejte", "take_cg": "podávejte",
        "drink": "pijte po malých doušcích", "drink_cg": "ať pije po malých doušcích",
        "per_plan": "podle rozpisu",
        "and": "a",
    },
    "sk": {
        "l1_main": "Ďakujeme, dnešný záznam je v očakávanom rozmedzí.",
        "l1_main_cg": "Ďakujeme, dnešný záznam {gen} je v očakávanom rozmedzí.",
        "l1_continue": "Pokračujte podľa odporúčaní.",
        "l1_earlier": "Ozvite sa skôr, ak sa {at}objaví {watch}.",
        "gap_l1": "Dnešný záznam chýba, vyplňte ho, prosím, keď to pôjde.",
        "gap_l1_earlier": "Ak sa necítite dobre, ozvite sa skôr.",
        "l2_main": "Váš záznam sme odovzdali tímu monitorovacieho centra, ozve sa vám {when}.",
        "l2_main_cg": "Záznam {gen} sme odovzdali tímu monitorovacieho centra, ozve sa vám {when}.",
        "gap_l2": "Niekoľko dní nám chýba váš záznam, preto sa vám ozve monitorovacie centrum {when}.",
        "when_next_day_end": "najneskôr do konca nasledujúceho pracovného dňa",
        "when_next_day": "nasledujúci pracovný deň",
        "l2_l3_watch": "Ak sa {at}objaví {watch}, volajte ihneď 155.",
        "l1_earlier_hint": "Ozvite sa skôr, ak: {watch}.",
        "l2_l3_watch_hint": "Volajte ihneď 155, ak: {watch}.",
        "l3_main": "Vaše ťažkosti je potrebné ešte dnes prebrať s lekárom MOÚ, ozve sa vám do 2 hodín.",
        "l3_main_cg": "Ťažkosti {gen} je potrebné ešte dnes prebrať s lekárom MOÚ, ozve sa vám do 2 hodín.",
        "l3_main_ooh": "Vaše ťažkosti je potrebné ešte dnes prebrať s lekárom, volajte ihneď službukonajúceho lekára MOÚ 724 590 848.",
        "l3_main_ooh_cg": "Ťažkosti {gen} je potrebné ešte dnes prebrať s lekárom, volajte ihneď službukonajúceho lekára MOÚ 724 590 848.",
        "meanwhile": "Dovtedy {action}.",
        "l4_ems": "Volajte ihneď 155 alebo choďte na urgentný príjem.",
        "l4_on_duty": "Volajte ihneď 155 alebo službukonajúceho lekára MOÚ 724 590 848.",
        "l4_wait_night": "Nečakajte do rána.",
        "l4_wait_day": "Nečakajte, kým to prejde.",
        "l4_wait_night_cg": "Stav {gen} je potrebné posúdiť okamžite, nečakajte do rána.",
        "l4_wait_day_cg": "Stav {gen} je potrebné posúdiť okamžite, nečakajte.",
        "med_list": "Vezmite si so sebou zoznam liekov.",
        "paralen": "Paralen neužívajte, kým vás nevyšetrí lekár.",
        "paralen_cg": "Paralen nepodávajte, kým {acc}nevyšetrí lekár.",
        "opioid_stop": "Ďalšie dávky liekov na bolesť teraz neužívajte.",
        "opioid_stop_cg": "Ďalšie dávky liekov na bolesť teraz nepodávajte.",
        "port": "Na port nesiahajte.",
        "palliative": "Môžete volať aj 24-hodinovú linku paliatívneho tímu.",
        "psych": "Ak by sa objavili myšlienky ublížiť si, volajte ihneď 155 alebo 112.",
        "caregiver": "Starostlivosť je náročná a je v poriadku požiadať o pomoc.",
        "anticoag": "Dávkovanie liekov na riedenie krvi nemeňte bez pokynu lekára.",
        "bp_l2": "Tlak si naďalej merajte ráno a večer.",
        "bp_l3": "O hodinu si tlak zmerajte znova v pokoji.",
        "pain_l3": "neužívajte ďalšie dávky nad rámec rozpisu",
        "pain_l3_cg": "nepodávajte ďalšie dávky nad rámec rozpisu",
        "take": "užívajte", "take_cg": "podávajte",
        "drink": "pite po malých dúškoch", "drink_cg": "nech pije po malých dúškoch",
        "per_plan": "podľa rozpisu",
        "and": "a",
    },
}

RELATIVE = {
    "cs": {"F": ("vaší maminky", "u ní ", "ji "), "M": ("vašeho tatínka", "u něj ", "ho "),
           "spouse_F": ("vaší manželky", "u ní ", "ji "), "spouse_M": ("vašeho manžela", "u něj ", "ho "),
           None: ("vašeho blízkého", "", "")},
    "sk": {"F": ("vašej mamy", "u nej ", "ju "), "M": ("vášho otca", "u neho ", "ho "),
           "spouse_F": ("vašej manželky", "u nej ", "ju "), "spouse_M": ("vášho manžela", "u neho ", "ho "),
           None: ("vášho blízkeho", "", "")},
}

MED_INDICATIONS = {
    "diarrhea": ("prujem", "hnack", "loperamid"),
    "vomit": ("nevoln", "zvrac", "vracan"),
    "ileus": ("zacp", "zapch"),
    "pain": ("bolest",),
}


@cache
def _rule_ids_by_text() -> dict[str, tuple[str, ...]]:
    """The engine passes the rules' patient texts (hint_*/safety_*), not rule ids: map them back via rules.yaml."""
    try:
        rules = yaml.safe_load(Path(__file__).with_name("rules.yaml").read_text(encoding="utf-8"))["rules"]
    except Exception:
        return {}
    entries = rules.items() if isinstance(rules, dict) else [(rule.get("id"), rule) for rule in rules if isinstance(rule, dict)]
    by_text: dict[str, tuple[str, ...]] = {}
    for rule_id, rule in entries:
        for key in ("hint_cs", "hint_sk", "safety_cs", "safety_sk"):
            if isinstance(rule, dict) and rule.get(key):
                text = normalize(rule[key]).strip(" .")
                by_text[text] = (*by_text.get(text, ()), rule_id)
    return by_text


def _rule_ids(hints: list[str], warning_signs: list[str]) -> list[str]:
    rule_ids = [hint.upper() for hint in hints if re.fullmatch(r"[A-Za-z]+(-[A-Za-z0-9]+)+", hint)]
    by_text = _rule_ids_by_text()
    return rule_ids + [rule_id for text in [*hints, *warning_signs] for rule_id in by_text.get(normalize(text).strip(" ."), ())]


def _topics(rule_ids: list[str], hints: list[str], warning_signs: list[str]) -> list[str]:
    found = [name for name, rules, _ in TOPICS if any(rule_id.startswith(rules) for rule_id in rule_ids if rules)]
    if found or rule_ids:
        return found
    text = " " + normalize(" ".join([*warning_signs, *hints])) + " "
    return [name for name, _, keywords in TOPICS if any(keyword in text for keyword in keywords)]


def _relative(lang: str, sex: str | None, filled_by: str | None) -> tuple[str, str, str]:
    key = sex if sex in ("F", "M") else None
    if key and filled_by and normalize(filled_by).startswith("manzel"):
        key = f"spouse_{key}"
    return RELATIVE[lang][key]


def _scheme(med: Lek) -> str:
    if DOSE.search(med.frekvence or ""):
        return med.frekvence
    return ", ".join(part for part in (med.davka, med.frekvence) if part)


def _prn_med(meds: list[Lek], topic: str) -> Lek | None:
    keywords = MED_INDICATIONS.get(topic, ())
    for med in meds:
        if med.pri_potizich and any(keyword in normalize(f"{med.lek} {med.indikace}") for keyword in keywords):
            return med
    return None


def _med_action(med: Lek, text: dict, caregiver: bool) -> str:
    name = med.lek[0].lower() + med.lek[1:]
    scheme = _scheme(med)
    verb = text["take_cg" if caregiver else "take"]
    return f"{name} {verb} {text['per_plan']} ({scheme})" if scheme else f"{name} {verb} {text['per_plan']}"


def _meanwhile(level: int, topics: list[str], rule_ids: list[str], meds: list[Lek], text: dict, caregiver: bool) -> list[str]:
    """Levels 2-3: one pre-agreed instruction quoted verbatim from leky, or a standard safety line. Never a new dose."""
    drink = text["drink_cg" if caregiver else "drink"]
    io_diarrhea = any(rule_id.startswith(IO_RULES) for rule_id in rule_ids)
    on_anticoagulant = any(drug in normalize(med.lek) for med in meds for drug in ANTICOAGULANTS)
    for topic in topics:
        med = _prn_med(meds, topic)
        if topic == "diarrhea":
            action = f"{_med_action(med, text, caregiver)} {text['and']} {drink}" if med and not io_diarrhea else drink
        elif topic == "vomit":
            action = f"{_med_action(med, text, caregiver)} {text['and']} {drink}" if med and level == 2 else drink
        elif topic in ("ileus", "pain") and med and level == 2:
            action = _med_action(med, text, caregiver)
        elif topic == "pain" and level == 3:
            action = text["pain_l3_cg" if caregiver else "pain_l3"]
        elif topic == "bleeding" and on_anticoagulant:
            return [text["anticoag"]]
        elif topic == "bp":
            return [text["bp_l3" if level == 3 else "bp_l2"]]
        elif topic == "caregiver" and level == 2:
            return [text["caregiver"]]
        else:
            continue
        return [text["meanwhile"].format(action=action) if level == 3 else action[0].upper() + action[1:] + "."]
    return []


def _when_next_day(contact: str | None, text: dict) -> str:
    if contact and "následující pracovní den" in contact and "do konce" not in contact:
        return text["when_next_day"]
    return text["when_next_day_end"]


def compose_reply(
    level: int,
    step: str | None,
    contact: str | None,
    lang: str,
    addressee: str,
    warning_signs: list[str] | None = None,
    followup: str | None = None,
    hints: list[str] | None = None,
    meds: list[Lek] | None = None,
    use_llm: bool = False,
    sex: str | None = None,
    filled_by: str | None = None,
) -> str:
    """Patient reply for one triage result (spec §8.9). warning_signs = the rules' patient hints, hints = rule ids or
    safety lines, sex/filled_by = how a caregiver refers to the patient. With use_llm the polished text is used only
    when it passes the validator."""
    lang = lang if lang in T else "cs"
    meds = meds or []
    args = (level, contact, lang, addressee, warning_signs or [], followup, hints or [], meds, sex, filled_by)
    text = _template(*args, engine_hint=True)
    problems = validate_patient_text(text, level, lang, meds, contact)
    if problems:
        plain = _template(*args, engine_hint=False)
        if not validate_patient_text(plain, level, lang, meds, contact):
            text, problems = plain, []
    if problems:
        log.warning("template reply failed validation: %s", problems)
    if not use_llm:
        return text
    try:
        from app.llm.polish import polish

        polished = polish(text, lang, level, addressee)
    except Exception:
        log.exception("polish failed")
        return text
    if not polished:
        return text
    problems = validate_patient_text(polished, level, lang, meds, contact)
    if followup and followup.strip() not in polished:
        problems.append("followup_missing")
    if problems:
        log.warning("polished reply rejected, template used: %s", problems)
        return text
    return polished


def _template(
    level: int,
    contact: str | None,
    lang: str,
    addressee: str,
    warning_signs: list[str],
    followup: str | None,
    hints: list[str],
    meds: list[Lek],
    sex: str | None,
    filled_by: str | None,
    engine_hint: bool,
) -> str:
    text = T[lang]
    caregiver = addressee != "pacient"
    gen, at, acc = _relative(lang, sex, filled_by) if caregiver else ("", "", "")
    rule_ids = _rule_ids(hints, warning_signs)
    topics = _topics(rule_ids, hints, warning_signs)
    gap = any("GAP" in rule_id for rule_id in rule_ids)
    palliative = any("paliativ" in normalize(hint) or "PALLIATIVE" in hint.upper() for hint in hints)
    watch_topic = next((topic for topic in topics if topic in WATCH[lang]), "default")
    if watch_topic == "pain" and any(opioid in normalize(med.lek) for med in meds for opioid in OPIOIDS):
        watch_topic = "opioid"
    known = _rule_ids_by_text()
    hint = next((sign.strip().rstrip(".") for sign in warning_signs if normalize(sign).strip(" .") in known), None) if engine_hint else None
    if hint and caregiver and SECOND_PERSON.search(hint):
        hint = None
    earlier = text["l1_earlier_hint"].format(watch=hint) if hint else text["l1_earlier"].format(at=at, watch=WATCH[lang][watch_topic])
    watch = text["l2_l3_watch_hint"].format(watch=hint) if hint else text["l2_l3_watch"].format(at=at, watch=WATCH[lang][watch_topic])
    if "psych" in topics:
        watch = text["psych"]
    cg = "_cg" if caregiver else ""
    followup = followup.strip() if followup else None
    out_of_hours = bool(contact and "724 590 848" in contact)

    # (priority, sentence): the 4 lowest priorities survive, in list order
    parts: list[tuple[int, str]] = []
    if level == 1:
        if followup:
            parts.append((0, followup))
        if gap:
            parts += [(1, text["gap_l1"]), (2, text["gap_l1_earlier"])]
        else:
            parts += [(1, text["l1_main" + cg].format(gen=gen)), (3, text["l1_continue"]), (2, earlier)]
    elif level in (2, 3):
        if followup:
            parts.append((0, followup))
        if level == 2:
            main = (text["gap_l2"] if gap else text["l2_main" + cg]).format(gen=gen, when=_when_next_day(contact, text))
        else:
            main = text[("l3_main_ooh" if out_of_hours else "l3_main") + cg].format(gen=gen)
        parts.append((1, main))
        parts += [(3, line) for line in _meanwhile(level, topics, rule_ids, meds, text, caregiver)]
        parts.append((2, watch))
        if palliative:
            parts.append((4, text["palliative"]))
    else:
        parts.append((0, text["l4_on_duty" if out_of_hours else "l4_ems"]))
        parts.append((1, text[("l4_wait_night" if out_of_hours else "l4_wait_day") + cg].format(gen=gen)))
        fever_on_chemo = "R-FEVER" in rule_ids or (
            "fever" in topics and any("chemoterap" in normalize(sign) for sign in warning_signs)
        )
        if fever_on_chemo:
            parts.append((2, text["paralen_cg"].format(acc=acc) if caregiver else text["paralen"]))
        if "opioid" in topics:
            parts.append((2, text["opioid_stop" + cg]))
        if "port" in topics:
            parts.append((3, text["port"]))
        if "psych" in topics:
            parts.append((2, text["psych"]))
        if palliative:
            parts.append((3, text["palliative"]))
        parts.append((5, text["med_list"]))
    keep = sorted(range(len(parts)), key=lambda index: (parts[index][0], index))[:4]
    return " ".join(parts[index][1] for index in sorted(keep))
