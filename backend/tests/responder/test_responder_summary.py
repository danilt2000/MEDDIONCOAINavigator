import re
import sys
import types
from datetime import date

from app.adapters.meddi_json import load_patient, load_patients
from app.context.builder import build_context
from app.models import Evidence, PatientContext, TriageOutput
from app.summary.summarizer import MAX_WORDS, build_summary, check_llm_text, word_count
from app.triage.validator import DIAGNOSIS, normalize

DAY_MONTH = re.compile(r"\b(\d{1,2})\. (\d{1,2})\.")


def output(patient, checkin, level=3, findings=("nález",), warnings=("varovný příznak",), quote=None) -> TriageOutput:
    return TriageOutput(
        checkin_id=checkin.checkin_id, patient_id=patient.patient_id, uroven=level, doporuceny_krok="telekonzultace",
        upozornit_tym=level > 1, doporuceny_kontakt=None, klicove_nalezy=list(findings), varovne_priznaky=list(warnings),
        zduvodneni="", doporuceni_pro_pacienta="", as_of=checkin.timestamp,
        dukazy=[Evidence(zdroj="zprava", citace=quote, checkin_id=checkin.checkin_id)] if quote else [],
    )


def leaky_context(patient, as_of) -> PatientContext:
    """Deliberately contains everything, also data after as_of: the summary itself must drop it."""
    return PatientContext(
        patient_id=patient.patient_id, as_of=as_of, age=patient.demografie.vek, sex=patient.demografie.pohlavi,
        lang=patient.demografie.jazyk, filled_by_default=patient.demografie.vyplnuje, diagnosis=patient.diagnoza.diagnoza,
        regimen=patient.lecba.rezim, intent=patient.lecba.zamer, meds=patient.leky, comorbidities=patient.komorbidity,
        advance_directive=patient.predem_vyslovena_prani, labs=patient.laboratore, exams=patient.vysetreni,
        team_events=patient.udalosti_tymu, recent_checkins=patient.checkiny,
    )


def dates_in(text: str, year: int) -> list[date]:
    return [date(year, int(month), int(day)) for day, month in DAY_MONTH.findall(text)]


def test_no_future_facts_and_word_limit_on_every_dev_checkin():
    for patient in load_patients("dev"):
        all_outputs = [output(patient, checkin, level=2 + index % 3) for index, checkin in enumerate(patient.checkiny)]
        for checkin in patient.checkiny:
            as_of = checkin.timestamp
            for ctx in (leaky_context(patient, as_of), build_context(patient, as_of)):
                summary = build_summary(patient, ctx, all_outputs, "eskalace")
                assert word_count(summary.text) <= MAX_WORDS, (checkin.checkin_id, summary.text)
                assert all(day <= as_of.date() for day in dates_in(summary.text, as_of.year)), (checkin.checkin_id, summary.text)
                assert all(fact.datum is None or fact.datum[:10] <= as_of.date().isoformat() for fact in summary.facts)
                assert summary.generated_by == "template"


def test_future_events_never_leak():
    patient = load_patient("ONC-007")
    c08 = next(checkin for checkin in patient.checkiny if checkin.checkin_id == "ONC-007-C08")
    summary = build_summary(patient, leaky_context(patient, c08.timestamp), [], "eskalace")
    assert "LVEF 44" not in summary.text
    assert "1450" not in summary.text
    assert "přerušen" not in summary.text


def test_onc_007_escalation_layout():
    patient = load_patient("ONC-007")
    checkins = {checkin.checkin_id: checkin for checkin in patient.checkiny}
    outputs = [
        output(patient, checkins["ONC-007-C06"], 2, ["otoky i ráno"], []),
        output(patient, checkins["ONC-007-C08"], 3, ["nově ortopnoe", "+3 kg za 7 dní"], ["ortopnoe", "rychlý přírůstek hmotnosti"], "spát na dvou polštářích"),
    ]
    as_of = checkins["ONC-007-C08"].timestamp
    summary = build_summary(patient, build_context(patient, as_of), outputs, "eskalace")
    lines = summary.text.splitlines()
    assert lines[0] == "ONC-007 · Hana D., 55 let · souhrn při eskalaci (2026-09-10, 07:30)"
    assert lines[1].startswith("Proč teď: nově ortopnoe") and "ORANŽOVÁ" in lines[1]
    assert any(line.startswith("Léčba: trastuzumab") for line in lines)
    assert "3. 9. 83,4 kg" in summary.text and "10. 9. 86,4 kg" in summary.text
    assert "(naměřeno)" in summary.text and "(pacient)" in summary.text and "(odhad systému)" in summary.text
    assert "Nehlásí:" in summary.text and "bolest na hrudi" in summary.nehlasi
    assert lines[-1] == "K posouzení lékařem: dnes – nově ortopnoe, +3 kg za 7 dní."


def test_application_summary_header():
    patient = load_patient("ONC-002")
    checkin = next(item for item in patient.checkiny if item.checkin_id == "ONC-002-C12")
    summary = build_summary(patient, build_context(patient, checkin.timestamp), [output(patient, checkin, 2)], "aplikace")
    assert "souhrn před aplikací C7" in summary.header
    assert summary.text.splitlines()[1].startswith("K rozhodnutí dnes:")


def test_caregiver_quote_marked():
    patient = load_patient("ONC-014")
    checkin = next(item for item in patient.checkiny if item.checkin_id == "ONC-014-C09")
    summary = build_summary(patient, build_context(patient, checkin.timestamp), [output(patient, checkin, 4)], "eskalace")
    assert "(dcera)" in summary.text
    assert "DVP:" in summary.text


def test_no_diagnosis_from_summary_itself():
    for patient in load_patients("dev"):
        checkin = patient.checkiny[-1]
        summary = build_summary(patient, build_context(patient, checkin.timestamp), [], "na_vyzadani")
        own_text = "\n".join([summary.proc_ted, summary.vyvoj, summary.nehlasi or "", summary.k_posouzeni])
        assert not DIAGNOSIS.search(normalize(own_text)), own_text


def _fake_writer(monkeypatch, text):
    module = types.ModuleType("app.llm.summary_writer")
    module.write_summary = lambda facts, header, lang="cs": text
    monkeypatch.setitem(sys.modules, "app.llm.summary_writer", module)


def test_llm_text_kept_only_when_numbers_and_layout_check_out(monkeypatch):
    patient = load_patient("ONC-007")
    checkin = next(item for item in patient.checkiny if item.checkin_id == "ONC-007-C08")
    ctx = build_context(patient, checkin.timestamp)
    outputs = [output(patient, checkin, 3, ["nově ortopnoe"], ["ortopnoe"])]
    deterministic = build_summary(patient, ctx, outputs, "eskalace")

    good = "Proč teď: nově ortopnoe, ORANŽOVÁ (odhad systému).\nVývoj: váha 3. 9. 83,4 kg → 10. 9. 86,4 kg (naměřeno).\nK posouzení lékařem: ortopnoe."
    _fake_writer(monkeypatch, good)
    summary = build_summary(patient, ctx, outputs, "eskalace", use_llm=True)
    assert summary.generated_by == "llm"
    assert summary.text == f"{deterministic.header}\n{good}"

    for bad in (
        good.replace("86,4", "88,1"),
        good.replace("10. 9.", "12. 9."),
        good + " Možná souvislost s léčbou.",
        good.replace("K posouzení lékařem: ortopnoe.", "Navrhuji snížit dávku."),
        good.replace("ortopnoe.", "ortopnoe, horečka a krvácení."),
        good.replace("K posouzení lékařem", "Laboratoř:\nK posouzení lékařem"),
        None,
    ):
        _fake_writer(monkeypatch, bad)
        summary = build_summary(patient, ctx, outputs, "eskalace", use_llm=True)
        assert summary.generated_by == "template", bad
        assert summary.text == deterministic.text


def test_check_llm_text_rejects_unknown_numbers():
    from app.models import SummaryFact

    facts = [SummaryFact(text="váha 3. 9. 83,4 kg → 10. 9. 86,4 kg", datum="2026-09-10", zdroj="naměřeno")]
    header = "ONC-007 · Hana D., 55 let · souhrn (2026-09-10, 07:30)"
    ok = f"{header}\nProč teď: váha 86,4 kg.\nK posouzení lékařem: váha."
    assert check_llm_text(ok, facts, header) == []
    assert any(problem.startswith("unknown_number") for problem in check_llm_text(ok.replace("86,4", "90"), facts, header))
