"""§13 critical moments of the dev set, replayed chronologically rules-only."""
import pytest

from app.adapters.meddi_json import load_patients
from app.eval.replay import replay

EXPECTED = {
    "ONC-001-C07": 4, "ONC-008-C09": 4,
    "ONC-004-C04": 2, "ONC-004-C05": 3, "ONC-004-C06": 4,
    "ONC-010-C02": 2, "ONC-010-C03": 3, "ONC-010-C04": 4,
    "ONC-011-C05": 3, "ONC-011-C08": 3, "ONC-011-C09": 4,
    "ONC-014-C09": 4, "ONC-014-C05": 3,
    "ONC-007-C06": 2, "ONC-007-C07": 2, "ONC-007-C08": 3,
    "ONC-013-C05": 3, "ONC-013-C06": 3,
    "ONC-018-C03": 3, "ONC-018-C04": 2,
    "ONC-002-C08": 3, "ONC-002-C12": 2,
    "ONC-009-C06": 3, "ONC-009-C12": 2,
    "ONC-016-C05": 3, "ONC-016-C06": 3,
    "ONC-017-C06": 1, "ONC-017-C07": 1, "ONC-017-C08": 2,
}


@pytest.fixture(scope="module")
def outputs():
    return {output.checkin_id: output for _, _, output in replay(list(load_patients("dev")), use_llm=False)}


@pytest.mark.parametrize("checkin_id, level", EXPECTED.items())
def test_critical_moment(outputs, checkin_id, level):
    assert outputs[checkin_id].uroven == level


def test_fever_in_nadir_out_of_hours(outputs):
    output = outputs["ONC-001-C07"]
    assert output.doporuceny_kontakt == "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)"
    assert "Paralen" in output.doporuceni_pro_pacienta


def test_refractory_pain_addresses_the_daughter(outputs):
    output = outputs["ONC-014-C05"]
    assert output.adresat == "pecujici"
    assert output.doporuceny_kontakt == "telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h"


def test_slovak_contradiction_follow_up(outputs):
    assert outputs["ONC-018-C03"].doplnujici_otazka == "Píšete, že máte hnačku asi 6× za deň – je to tak?"
    assert outputs["ONC-018-C03"].lang == "sk"
    assert "C-CONTRADICTION" in outputs["ONC-018-C03"].pravidla


def test_stable_patient_no_false_alarms(outputs):
    levels = {checkin_id: output.uroven for checkin_id, output in outputs.items() if checkin_id.startswith("ONC-005-")}
    assert levels.pop("ONC-005-C10") == 2
    assert set(levels.values()) == {1}
    assert outputs["ONC-005-C10"].doporuceny_kontakt == "monitorovací centrum – následující pracovní den"
