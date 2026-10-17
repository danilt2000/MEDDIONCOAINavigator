"""Symptom grades from the MEDDI adverse-effects questionnaire (odpoved_index) and measured temperature."""

from app.models import Checkin

AE_QUESTIONNAIRE = "nezadouci_ucinky"
SYMPTOMS: dict[str, list[tuple[str, int]]] = {
    "Průjem": [("prujem", 1)],
    "Horečka 38 °C a víc": [("teplota", 0)],
    "Nevolnost a zvracení": [("nevolnost", 1), ("zvraceni", 1)],
    "Mukozitida (afty v ústech)": [("afty", 1)],
    "Periferní neuropatie": [("brneni", 1)],
    "Kožní reakce na rukou a nohou": [("kuze", 1)],
    "Dušnost": [("dusnost", 1)],
    "Únava": [("unava", 1)],
    "Bolest": [("bol_hlava", 1), ("bol_hrud", 1), ("bol_bricho", 1), ("bol_klouby", 1)],
    "Nechutenství": [("nechutenstvi", 1)],
    "Zácpa": [("zacpa", 1)],
    "Krvácení": [("krvaceni", 0)],
    "Potíže s močením": [("moceni", 0)],
}
FEVER = "Horečka 38 °C a víc"
# NLU fact types of a chat message -> symptom row; VALUE_GRADES turn a number into grade 1-3 (below the first step = not reported)
FACT_SYMPTOMS = {
    "temperature_c": FEVER, "fever_reported": FEVER, "chills": FEVER,
    "stool_count_above_normal": "Průjem", "diarrhea": "Průjem", "diarrhea_refractory": "Průjem",
    "vomiting_episodes_24h": "Nevolnost a zvracení", "vomiting": "Nevolnost a zvracení", "antiemetic_failure": "Nevolnost a zvracení",
    "dyspnea_rest": "Dušnost", "dyspnea_exertion": "Dušnost", "orthopnea": "Dušnost",
    "pain_nrs": "Bolest", "abdominal_pain_nrs": "Bolest", "chest_pain_new": "Bolest", "headache_severe": "Bolest",
    "colicky_pain": "Bolest", "pain_refractory": "Bolest",
    "bleeding_site": "Krvácení", "nosebleed_minutes": "Krvácení", "blood_in_stool": "Krvácení", "black_stool": "Krvácení",
    "bleeding_uncontrolled": "Krvácení",
    "neuropathy_function_loss": "Periferní neuropatie", "neuropathy_persistent": "Periferní neuropatie",
    "skin_blisters": "Kožní reakce na rukou a nohou", "nail_fold_inflammation": "Kožní reakce na rukou a nohou",
    "weakness": "Únava", "reduced_intake": "Nechutenství", "liquids_only": "Nechutenství",
    "constipation_days": "Zácpa", "no_stool_no_gas": "Zácpa", "no_urine_hours": "Potíže s močením", "oliguria": "Potíže s močením",
}
VALUE_GRADES = {"temperature_c": (38, 39, 40), "stool_count_above_normal": (1, 4, 7), "vomiting_episodes_24h": (1, 3, 6),
                "pain_nrs": (1, 4, 7), "abdominal_pain_nrs": (1, 4, 7)}


def _fever_grade(celsius: float) -> int:
    return 0 if celsius < 38 else 1 if celsius < 39 else 2 if celsius < 40 else 3


def symptom_grades(checkin: Checkin) -> dict[str, int]:
    """Grade per symptom present in the check-in (grade = option index + offset; Ne/37 °C options give 0)."""
    indexes = {
        answer.otazka_id: answer.odpoved_index
        for fill in checkin.dotazniky
        if fill.dotaznik_id == AE_QUESTIONNAIRE
        for answer in fill.odpovedi
        if isinstance(answer.odpoved_index, int)
    }
    grades: dict[str, int] = {}
    for symptom, questions in SYMPTOMS.items():
        grade = max((indexes[question] + offset for question, offset in questions if question in indexes), default=0)
        if grade > 0:
            grades[symptom] = grade
    temperature = (checkin.vitalni_funkce or {}).get("teplota_c")
    if temperature is not None and _fever_grade(temperature.hodnota) > grades.get(FEVER, 0):
        grades[FEVER] = _fever_grade(temperature.hodnota)
    return grades


def fact_grades(facts: list) -> dict[str, int]:
    """Grade per symptom a chat message reports (its NLU facts): a number grades it, a bare mention is grade 1."""
    grades: dict[str, int] = {}
    for fact in facts:
        symptom = FACT_SYMPTOMS.get(fact.type)
        if symptom is None:
            continue
        number = fact.value if isinstance(fact.value, (int, float)) and not isinstance(fact.value, bool) else None
        steps = VALUE_GRADES.get(fact.type)
        grade = sum(number >= step for step in steps) if steps and number is not None else 1
        if grade > grades.get(symptom, 0):
            grades[symptom] = grade
    return grades


if __name__ == "__main__":
    from app.adapters.meddi_json import load_patient

    fever_checkin = next(checkin for checkin in load_patient("ONC-001").checkiny if checkin.checkin_id == "ONC-001-C07")
    grades = symptom_grades(fever_checkin)
    assert grades[FEVER] >= 1, grades
    print(grades)

    from app.models import Fact

    chat = fact_grades([Fact(type="temperature_c", value=39.2, quote="39,2"), Fact(type="fever_reported", quote="teplotu"),
                        Fact(type="stool_count_above_normal", value=2, quote="2x"), Fact(type="temperature_c", value=37.2, quote="37,2"),
                        Fact(type="weakness", value=True, quote="slabá"), Fact(type="other", value="afty", quote="afty")])
    assert chat == {FEVER: 2, "Průjem": 1, "Únava": 1}, chat
    assert fact_grades([Fact(type="temperature_c", value=37.4, quote="37,4")]) == {}
    print(chat)
