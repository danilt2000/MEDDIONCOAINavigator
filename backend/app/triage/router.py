"""Level × working hours → step, contact, notify flag, SLA (spec §8.2). No holiday calendar (ground truth ignores them)."""
from datetime import datetime, time, timedelta

from app.models import PRAGUE, Step

OPEN, CLOSE = time(7, 0), time(15, 30)

STEPS: dict[int, Step] = {1: "dalsi_sledovani", 2: "kontaktovat_tym", 3: "telekonzultace", 4: "neodkladna_pomoc"}
CONTACT_MC_IN_HOURS = "monitorovací centrum – vyřízení do konce následujícího pracovního dne"
CONTACT_MC_OUT_OF_HOURS = "monitorovací centrum – následující pracovní den"
CONTACT_TELE = "telekonzultace s lékařem MOÚ přes monitorovací centrum do 2 h"
CONTACT_ON_DUTY = "sloužící lékař MOÚ 724 590 848 – ihned"
CONTACT_EMS_IN_HOURS = "155 / urgentní příjem"
CONTACT_EMS_OUT_OF_HOURS = "155 / urgentní příjem (případně sloužící lékař MOÚ 724 590 848)"


def is_working_hours(at: datetime) -> bool:
    local = at.astimezone(PRAGUE) if at.tzinfo else at.replace(tzinfo=PRAGUE)
    return local.weekday() < 5 and OPEN <= local.time() < CLOSE


def _end_of_next_working_day(at: datetime) -> datetime:
    local = at.astimezone(PRAGUE) if at.tzinfo else at.replace(tzinfo=PRAGUE)
    day = local.date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, CLOSE, tzinfo=PRAGUE)


def route(level: int, at: datetime, missed_checkins: bool = False) -> tuple[Step, str | None, bool, datetime | None]:
    """(doporuceny_krok, doporuceny_kontakt, upozornit_tym, sla_do)."""
    in_hours = is_working_hours(at)
    if level <= 1:
        return STEPS[1], None, False, None
    if level == 2:
        contact = CONTACT_MC_IN_HOURS if in_hours or missed_checkins else CONTACT_MC_OUT_OF_HOURS
        return STEPS[2], contact, True, _end_of_next_working_day(at)
    if level == 3:
        if in_hours:
            return STEPS[3], CONTACT_TELE, True, at + timedelta(hours=2)
        return STEPS[3], CONTACT_ON_DUTY, True, at + timedelta(minutes=15)
    return STEPS[4], CONTACT_EMS_IN_HOURS if in_hours else CONTACT_EMS_OUT_OF_HOURS, True, at + timedelta(minutes=15)


def contact_category(contact: str | None) -> str:
    if not contact:
        return "none"
    if contact.startswith("155"):
        return "ems"
    if contact.startswith("sloužící"):
        return "on_duty"
    if contact.startswith("telekonzultace"):
        return "tele_2h"
    return "mc_next_day"
