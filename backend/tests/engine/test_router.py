from datetime import datetime

import pytest

from app.models import PRAGUE
from app.triage.router import contact_category, is_working_hours, route


def at(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=PRAGUE)   # 2026-09-07 is a Monday


@pytest.mark.parametrize("moment, expected", [
    (at(7, 6, 59), False), (at(7, 7, 0), True), (at(7, 15, 29), True), (at(7, 15, 30), False),
    (at(11, 14, 0), True), (at(12, 10, 0), False), (at(13, 10, 0), False),
    (at(28, 10, 0), True),                                     # 28. 9. holiday handled as a working day
])
def test_working_hours_boundaries(moment, expected):
    assert is_working_hours(moment) is expected


def test_level_1_has_no_contact():
    assert route(1, at(7, 10, 0)) == ("dalsi_sledovani", None, False, None)


def test_level_2_strings_and_sla():
    step, contact, notify, sla = route(2, at(7, 10, 0))
    assert (step, contact, notify) == ("kontaktovat_tym", "monitorovací centrum – vyřízení do konce následujícího pracovního dne", True)
    assert sla == at(8, 15, 30)
    assert route(2, at(11, 18, 25))[1] == "monitorovací centrum – následující pracovní den"
    assert route(2, at(11, 18, 25))[3] == at(14, 15, 30)       # Friday evening → Monday end of day
    assert route(2, at(13, 17, 0), missed_checkins=True)[1] == "monitorovací centrum – vyřízení do konce následujícího pracovního dne"


def test_level_3_and_4_strings():
    assert route(3, at(10, 10, 15))[1] == "telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h"
    assert route(3, at(10, 10, 15))[3] == at(10, 12, 15)
    assert route(3, at(9, 21, 52))[1] == "sloužící lékař MOÚ 724 590 848 – ihned"
    assert route(4, at(11, 7, 20))[1] == "155 / urgentní příjem"
    assert route(4, at(11, 6, 40))[1] == "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)"
    assert route(4, at(9, 21, 52))[:3] == ("neodkladna_pomoc", "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)", True)


def test_contact_categories():
    pairs = [(1, at(7, 10, 0)), (2, at(7, 10, 0)), (3, at(7, 10, 0)), (3, at(7, 20, 0)), (4, at(7, 20, 0))]
    assert [contact_category(route(level, moment)[1]) for level, moment in pairs] == ["none", "mc_next_day", "tele_2h", "on_duty", "ems"]
