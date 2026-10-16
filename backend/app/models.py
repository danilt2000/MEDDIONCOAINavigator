from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

PRAGUE = ZoneInfo("Europe/Prague")

Level = Literal[1, 2, 3, 4]
Step = Literal["dalsi_sledovani", "kontaktovat_tym", "telekonzultace", "neodkladna_pomoc"]
Lang = Literal["cs", "sk"]


def _at(day: date, hhmm: str) -> datetime:
    hours, minutes = (int(part) for part in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hours, minutes, tzinfo=PRAGUE)


class MeddiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Measurement(MeddiModel):
    hodnota: float
    zdroj: str


class Answer(MeddiModel):
    otazka_id: str
    otazka: str
    odpoved: str | int | list[str] | None
    odpoved_index: int | list[int] | None
    barva: str | None
    upozorneni: str | None


class QuestionnaireFill(MeddiModel):
    vyplneni_id: str
    dotaznik_id: str
    dotaznik_nazev: str
    odpovedi: list[Answer]
    nejvyssi_barva: str | None
    zobrazena_upozorneni: list[str] = []


class Checkin(MeddiModel):
    checkin_id: str
    patient_id: str
    datum: date
    cas: str
    den_sledovani: int
    cyklus: int | None = None
    den_cyklu: int | None = None
    stav: Literal["vyplneno", "nevyplneno"]
    vyplnil: str
    dotazniky: list[QuestionnaireFill] = []
    vitalni_funkce: dict[str, Measurement] | None = None
    zprava_pacienta: str | None = None
    prilohy: list[str] = []

    @property
    def timestamp(self) -> datetime:
        return _at(self.datum, self.cas)


class Demografie(MeddiModel):
    jmeno_fiktivni: str
    vek: int
    pohlavi: str
    jazyk: Lang
    kraj: str
    domacnost: str
    digitalni_gramotnost: str
    vyplnuje: str


class Diagnoza(MeddiModel):
    diagnoza: str
    mkn10: str
    stadium: str
    biomarkery: str
    datum_diagnozy: str


class Antropometrie(MeddiModel):
    vyska_cm: int
    vaha_kg_vychozi: float
    bmi: float


class Cyklus(MeddiModel):
    cyklus: int
    den_sledovani: int
    datum_d1: date


class Lecba(MeddiModel):
    zamer: str
    rezim: str
    leky: list[str]
    delka_cyklu: int | None
    cykly: list[Cyklus]
    poznamka: str


class Lek(MeddiModel):
    lek: str
    davka: str
    frekvence: str
    indikace: str
    typ: str
    od_dne: int | None = None
    do_dne: int | None = None
    pri_potizich: bool
    od_data: str | None = None
    do_data: str | None = None


class Lab(MeddiModel):
    patient_id: str
    odber_id: str
    datum: date
    cas: str
    den_sledovani: int
    misto: str
    kod: str
    test: str
    hodnota: float
    jednotka: str
    ref_min: float
    ref_max: float
    priznak: str

    @property
    def timestamp(self) -> datetime:
        return _at(self.datum, self.cas)


class Vysetreni(MeddiModel):
    datum: date
    den_sledovani: int
    vysetreni: str
    vysledek: str


class TeamEvent(MeddiModel):
    patient_id: str
    datum: date
    cas: str
    den_sledovani: int
    typ: str
    autor: str
    text: str

    @property
    def timestamp(self) -> datetime:
        return _at(self.datum, self.cas)


class Patient(MeddiModel):
    patient_id: str
    synteticka_data: bool
    sada: str
    nazev_scenare: str | None = Field(default=None, description="Orientation only. The engine never reads it.")
    vychazi_ze_scenare: str | None = Field(default=None, description="Orientation only. The engine never reads it.")
    obdobi_sledovani: dict[str, date]
    demografie: Demografie
    diagnoza: Diagnoza
    ecog_vychozi: int
    komorbidity: list[str]
    alergie: list[str]
    predem_vyslovena_prani: str | None
    antropometrie: Antropometrie
    lecba: Lecba
    leky: list[Lek]
    laboratore: list[Lab]
    vysetreni: list[Vysetreni]
    udalosti_tymu: list[TeamEvent]
    checkiny: list[Checkin]


class GroundTruth(MeddiModel):
    checkin_id: str
    patient_id: str
    uroven: Level
    doporuceny_krok: Step
    upozornit_tym: bool
    doporuceny_kontakt: str | None
    klicove_nalezy: list[str]
    varovne_priznaky: list[str]
    zduvodneni: str
    doporuceni_pro_pacienta: str


class PatientContext(BaseModel):
    patient_id: str
    as_of: datetime
    age: int
    sex: str
    lang: Lang
    filled_by_default: str
    diagnosis: str
    regimen: str
    intent: str
    cycle: int | None = None
    cycle_day: int | None = None
    in_nadir: bool = False
    chemo_window: bool = False
    drug_classes: list[str] = []
    meds: list[Lek] = []
    comorbidities: list[str] = []
    allergies: list[str] = []
    advance_directive: str | None = None
    labs: list[Lab] = []
    exams: list[Vysetreni] = []
    team_events: list[TeamEvent] = []
    recent_checkins: list[Checkin] = []
    baselines: dict[str, float] = {}


class Fact(BaseModel):
    type: str
    value: Any = None
    period_h: float | None = None
    certainty: str | None = None
    quote: str
    source: Literal["zprava", "priloha", "dotaznik", "chat"] = "zprava"


class NluResult(BaseModel):
    lang: Lang = "cs"
    author: str = "pacient"
    facts: list[Fact] = []
    negations: list[str] = []
    patient_questions: list[str] = []
    caregiver_strain: bool = False


class Evidence(BaseModel):
    zdroj: str
    citace: str
    checkin_id: str | None = None
    datum: str | None = None


class TriageOutput(BaseModel):
    checkin_id: str
    patient_id: str
    uroven: Level
    doporuceny_krok: Step
    upozornit_tym: bool
    doporuceny_kontakt: str | None
    klicove_nalezy: list[str]
    varovne_priznaky: list[str]
    zduvodneni: str
    doporuceni_pro_pacienta: str
    doplnujici_otazka: str | None = None
    pravidla: list[str] = []
    dukazy: list[Evidence] = []
    jistota: Literal["nizka", "stredni", "vysoka"] = "stredni"
    sla_do: datetime | None = None
    verze: str = "engine 0.1.0"
    lang: Lang = "cs"
    adresat: Literal["pacient", "pecujici"] = "pacient"
    zdroj: Literal["checkin", "chat"] = "checkin"
    as_of: datetime


class SummaryFact(BaseModel):
    text: str
    datum: str | None = None
    zdroj: str
    ref: str | None = None


class DoctorSummary(BaseModel):
    patient_id: str
    as_of: datetime
    reason: str
    header: str
    proc_ted: str
    lecba: str
    vyvoj: str
    laborator: str | None = None
    nehlasi: str | None = None
    k_posouzeni: str
    facts: list[SummaryFact] = []
    text: str
    generated_by: Literal["llm", "template"] = "template"


class LevelCard(BaseModel):
    uroven: Level
    krok: Step
    kontakt: str | None
    buttons: list[str] = []
    sla_do: datetime | None = None


class NavigatorReply(BaseModel):
    reply_text: str
    lang: Lang = "cs"
    level_card: LevelCard | None = None
    followup_question: str | None = None
    facts: list[Fact] = []
    cites: list[str] = []
    escalated: bool = False
    triage: TriageOutput | None = None


class TaskNote(BaseModel):
    at: datetime
    author: str
    text: str


class QueueTask(BaseModel):
    id: str
    patient_id: str
    checkin_id: str | None = None
    uroven: Level
    priority: Literal["routine", "urgent", "stat"]
    status: Literal["requested", "accepted", "in-progress", "completed"] = "requested"
    owner: str
    why: str
    out_of_hours: bool = False
    created: datetime
    sla_do: datetime | None = None
    notes: list[TaskNote] = []
