from app.models import Lek
from app.triage.validator import validate_patient_text

LOPERAMID_SK = Lek(
    lek="Loperamid", davka="2 mg", frekvence="4 mg pri prvej riedkej stolici, potom 2 mg každé 2 h až 12 h bez hnačky",
    indikace="oneskorená hnačka po irinotekane", typ="podpurny", pri_potizich=True,
)
ORAMORPH = Lek(lek="Morfin roztok (Oramorph)", davka="10 mg", frekvence="max 6× denně", indikace="průlomová bolest", typ="podpurny", pri_potizich=True)
TELE = "telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h"
MC = "monitorovací centrum – vyřízení do konce následujícího pracovního dne"
EMS_NIGHT = "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)"


def codes(problems: list[str]) -> set[str]:
    return {problem.split(":")[0] for problem in problems}


def test_valid_texts_pass():
    assert validate_patient_text("Děkujeme, dnešní záznam je v očekávaném rozmezí.", 1, "cs", [], None) == []
    assert validate_patient_text(
        "Váš záznam jsme předali týmu monitorovacího centra, ozve se vám do konce následujícího pracovního dne.", 2, "cs", [], MC
    ) == []
    assert validate_patient_text(
        "Volejte ihned 155 nebo sloužícího lékaře MOÚ 724 590 848. Nečekejte do rána.", 4, "cs", [], EMS_NIGHT
    ) == []


def test_level_2_to_4_need_contact_and_time():
    assert "missing_contact" in codes(validate_patient_text("Ozveme se vám ještě dnes.", 3, "cs", [], "sloužící lékař MOÚ 724 590 848 – ihned"))
    assert "missing_time" in codes(validate_patient_text("Informaci předáváme týmu monitorovacího centra.", 2, "cs", [], MC))
    assert "missing_contact" in codes(validate_patient_text("Volejte ihned.", 4, "cs", [], "155 / urgentní příjem"))


def test_level_4_starts_with_call_to_action():
    text = "Vaše obtíže vyžadují okamžité vyšetření. Volejte ihned 155."
    assert "level4_no_call_to_action" in codes(validate_patient_text(text, 4, "cs", [], "155 / urgentní příjem"))
    assert validate_patient_text("Volajte ihneď 155 alebo choďte na urgentný príjem.", 4, "sk", [], "155 / urgentní příjem") == []


def test_diagnosis_words_blocked_cs_and_sk():
    for word in ["febrilní neutropenie", "sepse", "kolitida", "srdeční selhání", "trombóza", "embolie", "ketoacidóza", "infarkt", "metastáza"]:
        assert "diagnosis_word" in codes(validate_patient_text(f"Může jít o {word}.", 1, "cs", [], None)), word
    for word in ["sepsa", "kolitída", "srdcové zlyhanie", "embólia", "metastázy"]:
        assert "diagnosis_word" in codes(validate_patient_text(f"Môže ísť o {word}.", 1, "sk", [], None)), word
    assert validate_patient_text("Vezměte si s sebou seznam léků.", 1, "cs", [], None) == []


def test_doses_only_verbatim_from_meds():
    quoted = "Loperamid užívajte podľa rozpisu (4 mg pri prvej riedkej stolici, potom 2 mg každé 2 h až 12 h bez hnačky)."
    assert "dose_not_in_meds" not in codes(validate_patient_text(quoted, 1, "sk", [LOPERAMID_SK], None))
    assert "dose_not_in_meds" in codes(validate_patient_text("Užite 8 mg loperamidu.", 1, "sk", [LOPERAMID_SK], None))
    assert "dose_not_in_meds" in codes(validate_patient_text("Podejte 20 mg Oramorphu.", 1, "cs", [ORAMORPH], None))
    assert "dose_not_in_meds" in codes(validate_patient_text("Vezměte si 2 tablety.", 1, "cs", [], None))


def test_no_new_medicine_but_paralen_warning_allowed():
    assert "new_medicine" in codes(validate_patient_text("Vezměte si Ibalgin.", 1, "cs", [ORAMORPH], None))
    assert validate_patient_text("Paralen neužívejte, dokud vás nevyšetří lékař.", 1, "cs", [], None) == []
    assert "new_medicine" not in codes(validate_patient_text("Oramorph podávejte podle rozpisu.", 1, "cs", [ORAMORPH], None))


def test_no_dose_change_instructions():
    assert "treatment_change" in codes(validate_patient_text("Zvyšte si dávku morfinu.", 1, "cs", [ORAMORPH], None))
    assert "treatment_change" in codes(validate_patient_text("Podejte jí ještě jednu dávku.", 1, "cs", [ORAMORPH], None))
    assert "treatment_change" not in codes(validate_patient_text("Další dávky léků na bolest teď nepodávejte.", 1, "cs", [], None))


def test_reassurance_blocked_from_level_2():
    text = "Nemusíte se bát, váš záznam jsme předali týmu monitorovacího centra, ozve se vám zítra."
    assert "reassurance" in codes(validate_patient_text(text, 2, "cs", [], MC))
    assert "reassurance" not in codes(validate_patient_text("Nebojte, je to v očekávaném rozmezí.", 1, "cs", [], None))


def test_language_check():
    assert "wrong_language" in codes(validate_patient_text("Pokud se objeví horečka, volejte 155.", 1, "sk", [], None))
    assert "wrong_language" in codes(validate_patient_text("Ak sa objaví horúčka, volajte 155.", 1, "cs", [], None))
    assert validate_patient_text("Ak sa objaví horúčka, volajte ihneď 155.", 1, "sk", [], None) == []


def test_sentence_limit():
    text = "Děkujeme. Pokračujte. Pijte. Odpočívejte. Važte se."
    assert "too_many_sentences" in codes(validate_patient_text(text, 1, "cs", [], None))
