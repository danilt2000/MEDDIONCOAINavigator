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


if __name__ == "__main__":
    from app.adapters.meddi_json import load_patient

    fever_checkin = next(checkin for checkin in load_patient("ONC-001").checkiny if checkin.checkin_id == "ONC-001-C07")
    grades = symptom_grades(fever_checkin)
    assert grades[FEVER] >= 1, grades
    print(grades)
