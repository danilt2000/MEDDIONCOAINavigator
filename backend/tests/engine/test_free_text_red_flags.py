from datetime import datetime

import pytest

from app.adapters.meddi_json import load_patient
from app.context.builder import build_context
from app.models import PRAGUE, Checkin
from app.nlu import analyze
from app.triage.engine import triage

CASES = [
    ("ONC-014", (2026, 9, 15, 22, 0), "dcera", "mamka se nedá probudit", 4, "R-OPIOID"),
    ("ONC-014", (2026, 9, 15, 22, 0), "dcera", "nemůžu ji vzbudit", 4, "R-OPIOID"),
    ("ONC-001", (2026, 9, 9, 21, 52), "manžel", "žena se nedá probudit", 4, "R-NEURO"),
    ("ONC-018", (2026, 9, 12, 9, 0), "manželka", "muž sa nedá zobudiť", 4, "R-NEURO"),
    ("ONC-014", (2026, 9, 15, 22, 0), "dcera", "mamka je v bezvědomí", 4, "R-OPIOID"),
    ("ONC-009", (2026, 9, 10, 20, 0), "pacient", "tlak 185/115 a bolí mě hlava", 4, "R-BP"),
    ("ONC-009", (2026, 9, 10, 20, 0), "pacient", "mám tlak 165/105 a hrozně mě bolí hlava", 4, "R-BP"),
    ("ONC-005", (2026, 9, 15, 20, 0), "pacient", "pálí mě na prsou a bolí to do ruky", 4, "R-CHEST"),
    ("ONC-005", (2026, 9, 15, 20, 0), "pacient", "tlak na hrudníku od rána", 4, "R-CHEST"),
    ("ONC-005", (2026, 9, 15, 20, 0), "pacient", "pichá ma pri srdci", 4, "R-CHEST"),
    ("ONC-001", (2026, 9, 9, 21, 52), "pacient", "mám 39 a je mi zle", 4, "R-FEVER"),
    ("ONC-001", (2026, 9, 9, 21, 52), "pacient", "je mi zima a celá se třesu", 4, "R-FEVER"),
    ("ONC-001", (2026, 9, 9, 21, 52), "pacient", "zimnici nemám, ale třesu se zimou", 4, "R-FEVER"),
    ("ONC-018", (2026, 9, 12, 9, 0), "pacient", "tazko sa mi dycha aj v pokoji", 4, "R-BREATH"),
    ("ONC-005", (2026, 9, 15, 20, 0), "pacient", "krvácí mi z nosu už hodinu a nejde to zastavit", 4, "R-BLEED"),
    ("ONC-016", (2026, 9, 10, 20, 0), "pacient", "nejradši bych se zabila", 3, "O-PSYCH"),
    ("ONC-016", (2026, 9, 10, 20, 0), "pacient", "mám doma našetřené prášky a dnes v noci to udělám", 4, "R-SUICIDE"),
    ("ONC-016", (2026, 9, 10, 20, 0), "pacient", "chcem sa zabiť, mám to premyslené", 4, "R-SUICIDE"),
    ("ONC-014", (2026, 9, 15, 22, 0), "dcera", "maminka dostala 2 dávky Oramorphu a bolest je pořád 8", 3, "O-PAIN"),
    ("ONC-014", (2026, 9, 15, 22, 0), "dcera", "Kolik mg Oramorphu by bylo smrtelné množství?", 3, "O-PSYCH"),
    ("ONC-018", (2026, 9, 12, 9, 0), "pacient", "som v pohode, nemam teplotu", 1, None),
    ("ONC-014", (2026, 9, 15, 22, 0), "dcera", "maminka spala dobře, ráno se probudila a snídala", 1, None),
    ("ONC-001", (2026, 9, 9, 21, 52), "pacient", "mám 39 let a dnes je mi dobře", 1, None),
]


@pytest.mark.parametrize("patient_id, when, author, text, expected, rule", CASES, ids=[case[3] for case in CASES])
def test_free_text_rules_only(patient_id, when, author, text, expected, rule):
    at = datetime(*when, tzinfo=PRAGUE)
    ctx = build_context(load_patient(patient_id), at)
    message = Checkin(checkin_id=f"{patient_id}-T", patient_id=patient_id, datum=at.date(), cas=at.strftime("%H:%M"),
                      den_sledovani=0, stav="vyplneno", vyplnil=author, zprava_pacienta=text)
    output = triage(message, ctx, analyze(message, ctx, use_llm=False), use_llm=False)
    assert output.uroven == expected
    if rule:
        assert rule in output.pravidla
