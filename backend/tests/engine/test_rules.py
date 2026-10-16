"""Every hard rule: positive, boundary and negative case (spec §8.3, §16)."""
import pytest
from engine_helpers import WEDNESDAY_EVENING, checkin, context, level, run

from app.models import Measurement, TeamEvent

BASE = {"pocit": 1, "sobestacnost": 0}


def ans(**items):
    return {**BASE, **items}


# --- red ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("vitals, message, chemo, expected", [
    ({"teplota_c": 38.0}, None, True, 4),                     # boundary: exactly 38.0 in the chemo window
    ({"teplota_c": 37.9}, None, True, 1),                     # just below
    ({"teplota_c": 36.6}, "Večer mi je zima, třesu se", True, 4),   # chills alone
    ({"teplota_c": 38.4}, None, False, 2),                    # outside the window: §15 default
    ({"teplota_c": 39.2}, None, False, 3),
    (None, "mam 38,4 a trese me zima", True, 4),              # text only, no diacritics
    (None, "Teplotu nemám, jen únava.", True, 1),             # negated
])
def test_r_fever(vitals, message, chemo, expected):
    assert level(checkin(vitals=vitals, message=message), context(chemo=chemo, nadir=chemo)) == expected


def test_r_fever_from_questionnaire_answer():
    assert level(checkin(ans(ucinky=[5], teplota=1)), context(chemo=True)) == 4
    assert level(checkin(ans(ucinky=[5], teplota=0)), context(chemo=True)) == 1


@pytest.mark.parametrize("answers, vitals, message, expected", [
    (ans(dusnost=3), None, None, 4),
    (ans(dusnost=2), None, None, 2),
    (ans(), {"spo2": 89}, None, 4),
    (ans(), {"spo2": 90}, None, 3),                           # boundary: < 90 is red, 90–91 orange
    (ans(), {"spo2": 95}, None, 1),
    (ans(), None, "Dusim se i v klidu", 4),
])
def test_r_breath(answers, vitals, message, expected):
    assert level(checkin(answers, vitals, message), context()) == expected


def test_r_chest():
    assert level(checkin(ans(bol_hrud=1)), context()) == 4
    assert level(checkin(ans(bol_hrud=0)), context()) == 1   # long-standing, treated chest pain
    assert level(checkin(message="Od rána mě bolí na hrudi."), context()) == 4
    assert level(checkin(message="Bolest na hrudi nemám."), context()) == 1


@pytest.mark.parametrize("message, expected", [
    ("Maminka je zmatená, neví kde je.", 4),
    ("Měl záchvat, celý se třásl.", 4),
    ("Nemůže hýbat pravou rukou.", 4),
    ("Je trochu unavená, jinak v pořádku.", 1),
])
def test_r_neuro(message, expected):
    assert level(checkin(message=message, filled_by="dcera"), context()) == expected


@pytest.mark.parametrize("message, answers, classes, expected", [
    ("Na papíře krev po stolici.", ans(), [], 4),
    ("Stolice je černá jako dehet.", ans(), [], 4),
    ("Krvácel jsem z nosu asi 30 minut.", ans(), [], 4),
    ("Krvacal som z nosa asi 5 minut, potom prestalo.", ans(ucinky=[8], krvaceni=1), [], 1),   # boundary: < 20 min
    ("Průjem, ale bez krve.", ans(ucinky=[1], stolice_typ=[0], prujem=0), [], 1),           # negation
    ("Upadla jsem a uhodila se do hlavy.", ans(), ["anticoagulant"], 4),
    ("Upadla jsem a uhodila se do hlavy.", ans(), [], 1),
])
def test_r_bleed(message, answers, classes, expected):
    assert level(checkin(answers, message=message), context(classes)) == expected


@pytest.mark.parametrize("answers, message, classes, expected", [
    (ans(ucinky=[1], stolice_typ=[0], prujem=2), None, [], 4),
    (ans(), "průjem 7x za den", [], 4),                      # boundary: ≥ 7
    (ans(), "průjem 6x za den", [], 2),                      # 4–6 on other treatment: grade 2
    (ans(), "průjem 6x za den", ["fluoropyrimidine"], 3),    # O-DIARRHEA-RISK
    (ans(ucinky=[1], stolice_typ=[0], prujem=0), None, [], 1),
    (ans(ucinky=[1], stolice_typ=[0], prujem=0), None, ["immunotherapy"], 2),   # Y-IO-DIARRHEA
])
def test_r_diarrhea(answers, message, classes, expected):
    assert level(checkin(answers, message=message), context(classes)) == expected


@pytest.mark.parametrize("answers, message, expected", [
    (ans(ucinky=[0], nnz_typ=[2], zvraceni=2), None, 4),
    (ans(), "Zvracela jsem 6x.", 4),                         # > 5
    (ans(), "Zvracela jsem 5x, ale piju.", 2),               # boundary: 3–5 while drinking
    (ans(), "Zvracim po vsem i po vode 5x za den.", 3),      # 3–5 and cannot keep fluids
    (ans(ucinky=[0], nnz_typ=[2], zvraceni=0), None, 1),
])
def test_r_vomit(answers, message, expected):
    assert level(checkin(answers, message=message), context()) == expected


@pytest.mark.parametrize("vitals, message, expected", [
    (None, "Od včera večer nemočila.", 4),
    (None, "Nemočím 6 hodin.", 3),                           # boundary: ≤ 10 h
    ({"tk_sys": 89, "tk_dia": 55}, None, 4),
    ({"tk_sys": 90, "tk_dia": 60}, None, 1),
    (None, "Ráno jsem omdlela v koupelně.", 4),
])
def test_r_dehyd(vitals, message, expected):
    assert level(checkin(vitals=vitals, message=message), context()) == expected


def test_r_ileus():
    assert level(checkin(ans(ucinky=[1, 0], stolice_typ=[1], zacpa=3, nnz_typ=[2], zvraceni=0)), context()) == 4
    assert level(checkin(ans(ucinky=[1], stolice_typ=[1], zacpa=3)), context()) == 3
    assert level(checkin(ans(ucinky=[1], stolice_typ=[1], zacpa=1), message="Pořád nic, ale plyny odcházejí, nezvracím."), context()) == 2


@pytest.mark.parametrize("vitals, answers, classes, expected", [
    ({"tk_sys": 180, "tk_dia": 100}, ans(), [], 4),
    ({"tk_sys": 170, "tk_dia": 110}, ans(), [], 4),
    ({"tk_sys": 179, "tk_dia": 109}, ans(), [], 1),
    ({"tk_sys": 165, "tk_dia": 100}, ans(ucinky=[3], bolesti_typ=[0], bol_hlava=2), [], 4),
    ({"tk_sys": 160, "tk_dia": 95}, ans(), ["antiangiogenic"], 3),
    ({"tk_sys": 159, "tk_dia": 99}, ans(), ["antiangiogenic"], 2),
])
def test_r_bp(vitals, answers, classes, expected):
    assert level(checkin(answers, vitals), context(classes)) == expected


def test_r_dka():
    answers = ans(ucinky=[0, 3], nnz_typ=[2], zvraceni=0, bolesti_typ=[2], bol_bricho=0)
    assert level(checkin(answers, {"dechova_frekvence": 24}), context(comorbidities=["Diabetes mellitus 2. typu"])) == 4
    assert level(checkin(answers, {"dechova_frekvence": 24}), context()) == 1
    assert level(checkin(answers, {"dechova_frekvence": 18}), context(comorbidities=["Diabetes mellitus 2. typu"])) == 1


def test_r_opioid():
    assert level(checkin(vitals={"dechova_frekvence": 8}), context(["opioid"])) == 4
    assert level(checkin(message="Mamka je hodně spavá, skoro nereaguje.", filled_by="dcera"), context(["opioid"])) == 4
    assert level(checkin(vitals={"dechova_frekvence": 14}), context(["opioid"])) == 1


def test_r_opioid_red_despite_advance_directive():
    output = run(checkin(vitals={"dechova_frekvence": 8}, message="Mamka dýchá pomalu.", filled_by="dcera"),
                 context(["opioid"], directive="Nepřeje si resuscitaci", intent="symptomatická paliativní péče"))
    assert output.uroven == 4
    assert "155" in output.doporuceni_pro_pacienta


def test_r_suicide_and_o_psych():
    assert level(checkin(message="Mám doma našetřené prášky a vím, jak to udělám."), context()) == 4
    assert level(checkin(message="Občas si říkám, že by bylo lepší se ráno neprobudit. Ale nic bych si neudělala."), context()) == 3
    assert level(checkin(forms={"psychoonkologicky_screening": {"uzkost": 3, "depresivita": 3, "zvladani": 8, "sebevrazda": 0}}), context()) == 3
    assert level(checkin(message="Připadám si k ničemu, nemá cenu se snažit."), context()) == 3
    assert level(checkin(message="pripadam si k nicemu nema cenu se snazit"), context()) == 3


# --- orange ------------------------------------------------------------------------------------------------------
def test_o_general():
    assert level(checkin(ans(pocit=4)), context()) == 3
    assert level(checkin(ans(pocit=3)), context()) == 1


def test_o_breath_orthopnoea_and_spo2_drop():
    assert level(checkin(message="V noci musím spát na dvou polštářích."), context()) == 3
    assert level(checkin(vitals={"spo2": 93}), context(baselines={"spo2": 96})) == 3
    assert level(checkin(vitals={"spo2": 94}), context(baselines={"spo2": 96})) == 1


def test_o_io_diarrhea_pain():
    answers = ans(ucinky=[1, 3], stolice_typ=[0], prujem=0, bolesti_typ=[2], bol_bricho=0)
    assert level(checkin(answers), context(["immunotherapy"])) == 3
    assert level(checkin(answers), context()) == 1


def test_o_intake():
    assert level(checkin(ans(ucinky=[0], nnz_typ=[1], nevolnost=2)), context()) == 3
    liquids = ans(ucinky=[2], afty=2)
    pain_bad = {"bolest_analgeticka_terapie": {"nrs": 6, "spokojenost": 1, "sos": 2}}
    assert level(checkin(liquids, forms=pain_bad), context()) == 3
    assert level(checkin(liquids), context()) == 2


def test_o_bleed_anticoag():
    answers = ans(ucinky=[8], krvaceni=1, krvaceni_popis="Dásně při čištění zubů")
    assert level(checkin(answers), context(["anticoagulant"])) == 3
    assert level(checkin(message="Na rukou mám modřiny."), context(["anticoagulant"])) == 3


def test_o_dvt():
    assert level(checkin(message="Levé lýtko je oteklé a bolí."), context()) == 3


@pytest.mark.parametrize("pain, expected", [
    ({"nrs": 8, "spokojenost": 1, "sos": 2}, 3),
    ({"nrs": 6, "spokojenost": 1, "sos": 1}, 2),
    ({"nrs": 3, "spokojenost": 0, "sos": 3}, 2),             # ≥ 3 rescue doses
    ({"nrs": 4, "spokojenost": 0, "sos": 1}, 1),             # controlled
])
def test_o_pain(pain, expected):
    assert level(checkin(forms={"bolest_analgeticka_terapie": pain}), context()) == expected


def test_o_hypo_and_io_endo():
    assert level(checkin(vitals={"glykemie_mmol_l": 3.6}), context(["insulin"])) == 3
    assert level(checkin(vitals={"glykemie_mmol_l": 3.6}), context()) == 1
    assert level(checkin(message="Mám pořád žízeň a často močím."), context(["immunotherapy"])) == 3


# --- yellow, context, trends, gaps -------------------------------------------------------------------------------
def test_y_glucose_on_steroids():
    assert level(checkin(vitals={"glykemie_mmol_l": 17.8}, message="mám pořád žízeň a chodím často čůrat"), context(["corticosteroid"])) == 2
    assert level(checkin(vitals={"glykemie_mmol_l": 14.1}), context(["corticosteroid"])) == 1


def test_y_neuro_and_team_stopped_drug():
    answers = ans(ucinky=[4], brneni=1)
    assert level(checkin(answers), context(["neurotoxic"])) == 2
    stopped = TeamEvent(patient_id="T-001", datum=checkin().datum, cas="08:00", den_sledovani=9, typ="zmena_lecby", autor="lékař",
                        text="Od C7 oxaliplatina vynechána pro neuropatii.")
    assert level(checkin(answers), context(["neurotoxic"], team_events=[stopped])) == 1


def test_y_tinnitus_on_platinum():
    assert level(checkin(message="Trochu mi píská v uších."), context(["platinum"])) == 2


def test_y_caregiver_and_adherence():
    assert level(checkin(message="Já už nevím, jak to zvládat, nespím.", filled_by="dcera"), context()) == 2
    assert level(checkin(message="Tablety jsem pár dní vynechala."), context()) == 2


def test_contradiction_message_beats_questionnaire_in_slovak():
    output = run(checkin(ans(ucinky=[7], unava=1), message="od vcera mam hnacku asi 6 krat, slaby som"), context(["irinotecan"], lang="sk"))
    assert output.uroven == 3
    assert "C-CONTRADICTION" in output.pravidla
    assert output.doplnujici_otazka == "Píšete, že máte hnačku asi 6× za deň – je to tak?"


def test_missed_checkins_gap():
    missed = [checkin(status="nevyplneno", checkin_id=f"T-001-C0{number}") for number in (1, 2)]
    third = checkin(status="nevyplneno", checkin_id="T-001-C03")
    assert run(missed[0], context()).uroven == 1
    assert run(missed[1], context(recent=missed[:1])).uroven == 1
    output = run(third, context(recent=missed))
    assert output.uroven == 2
    assert output.doporuceny_kontakt == "monitorovací centrum – vyřízení do konce následujícího pracovního dne"
    assert run(missed[1], context(["immunotherapy"], recent=missed[:1])).uroven == 2   # high risk: earlier


def test_out_of_hours_orange_goes_to_on_duty_doctor():
    output = run(checkin(ans(pocit=4), at=WEDNESDAY_EVENING), context(at=WEDNESDAY_EVENING))
    assert output.doporuceny_kontakt == "sloužící lékař MOÚ 724 590 848 – ihned"


def test_output_shape_for_doctor():
    item = checkin(vitals={"teplota_c": 38.4}, message="naměřila jsem 38,4", at=WEDNESDAY_EVENING)
    item.vitalni_funkce["tepova_frekvence"] = Measurement(hodnota=108, zdroj="test")
    output = run(item, context(chemo=True, nadir=True, at=WEDNESDAY_EVENING))
    assert output.uroven == 4 and output.upozornit_tym and output.doporuceny_krok == "neodkladna_pomoc"
    assert output.pravidla[0] == "R-FEVER"
    assert any("38,4" in finding for finding in output.klicove_nalezy)
    assert any(evidence.citace == "naměřila jsem 38,4" for evidence in output.dukazy)
    assert output.doporuceni_pro_pacienta.startswith("Volejte ihned")
