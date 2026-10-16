export type Level = 1 | 2 | 3 | 4;
export type Step = 'dalsi_sledovani' | 'kontaktovat_tym' | 'telekonzultace' | 'neodkladna_pomoc';
export type Lang = 'cs' | 'sk';
export type Author = 'pacient' | 'pecujici';

export interface Measurement {
  hodnota: number;
  zdroj: string;
}

export interface Answer {
  otazka_id: string;
  otazka: string;
  odpoved: string | number | string[] | null;
  odpoved_index: number | number[] | null;
  barva: string | null;
  upozorneni: string | null;
}

export interface QuestionnaireFill {
  vyplneni_id: string;
  dotaznik_id: string;
  dotaznik_nazev: string;
  odpovedi: Answer[];
  nejvyssi_barva: string | null;
  zobrazena_upozorneni: string[];
}

export interface CheckinInput {
  checkin_id?: string;
  patient_id: string;
  datum?: string;
  cas?: string;
  den_sledovani?: number;
  cyklus?: number | null;
  den_cyklu?: number | null;
  stav: 'vyplneno' | 'nevyplneno';
  vyplnil: string;
  dotazniky: QuestionnaireFill[];
  vitalni_funkce?: Record<string, Measurement> | null;
  zprava_pacienta?: string | null;
  prilohy?: string[];
}

export interface Evidence {
  zdroj: string;
  citace: string;
  checkin_id?: string | null;
  datum?: string | null;
}

export interface TriageOutput {
  checkin_id: string;
  patient_id: string;
  uroven: Level;
  doporuceny_krok: Step;
  upozornit_tym: boolean;
  doporuceny_kontakt: string | null;
  klicove_nalezy: string[];
  varovne_priznaky: string[];
  zduvodneni: string;
  doporuceni_pro_pacienta: string;
  doplnujici_otazka: string | null;
  pravidla: string[];
  dukazy: Evidence[];
  jistota: 'nizka' | 'stredni' | 'vysoka';
  sla_do: string | null;
  verze: string;
  lang: Lang;
  adresat: 'pacient' | 'pecujici';
  zdroj: 'checkin' | 'chat';
  as_of: string;
}

export interface GroundTruth {
  checkin_id: string;
  patient_id: string;
  uroven: Level;
  doporuceny_krok: Step;
  upozornit_tym: boolean;
  doporuceny_kontakt: string | null;
  klicove_nalezy: string[];
  varovne_priznaky: string[];
  zduvodneni: string;
  doporuceni_pro_pacienta: string;
}

export interface Lek {
  lek: string;
  davka: string;
  frekvence: string;
  indikace: string;
  typ: string;
  pri_potizich: boolean;
  od_data?: string | null;
  do_data?: string | null;
}

export interface PatientContext {
  patient_id: string;
  as_of: string;
  age: number;
  sex: string;
  lang: Lang;
  filled_by_default: string;
  diagnosis: string;
  regimen: string;
  intent: string;
  cycle: number | null;
  cycle_day: number | null;
  in_nadir: boolean;
  chemo_window: boolean;
  drug_classes: string[];
  meds: Lek[];
  comorbidities: string[];
  allergies: string[];
  advance_directive: string | null;
  baselines: Record<string, number>;
}

export interface TaskNote {
  at: string;
  author: string;
  text: string;
}

export interface QueueTask {
  id: string;
  patient_id: string;
  checkin_id: string | null;
  uroven: Level;
  priority: 'routine' | 'urgent' | 'stat';
  status: 'requested' | 'accepted' | 'in-progress' | 'completed';
  owner: string;
  why: string;
  out_of_hours: boolean;
  created: string;
  sla_do: string | null;
  notes: TaskNote[];
}

export interface QueueItem extends QueueTask {
  patient_name: string;
  age: number;
  regimen: string;
  cycle_day: number | null;
}

export interface PatientListItem {
  patient_id: string;
  dataset: string;
  name: string;
  age: number;
  sex: string;
  lang: Lang;
  diagnosis: string;
  regimen: string;
  cycle: number | null;
  cycle_day: number | null;
  risk_badges: string[];
  filled_by: string;
  last_level: Level | null;
  last_checkin_at: string | null;
  open_task: QueueTask | null;
}

export interface PatientDetail extends PatientListItem {
  stage: string;
  icd10: string;
  intent: string;
  ecog: number;
  comorbidities: string[];
  allergies: string[];
  advance_directive: string | null;
  meds: Lek[];
  monitoring: { od: string; do: string };
}

export interface TimelineItem {
  kind: 'checkin' | 'lab' | 'team_event' | 'exam' | 'chat' | 'missed';
  at: string;
  title: string;
  detail: string;
  level?: Level | null;
  ref: string;
}

export interface TrendPoint {
  at: string;
  value: number;
  source: string;
}

export interface Trend {
  metric: string;
  unit: string;
  points: TrendPoint[];
}

export interface SummaryFact {
  text: string;
  datum: string | null;
  zdroj: string;
  ref: string | null;
}

export interface DoctorSummary {
  patient_id: string;
  as_of: string;
  reason: string;
  header: string;
  proc_ted: string;
  lecba: string;
  vyvoj: string;
  laborator: string | null;
  nehlasi: string | null;
  k_posouzeni: string;
  facts: SummaryFact[];
  text: string;
  generated_by: 'llm' | 'template';
}

export interface Fact {
  type: string;
  value: unknown;
  quote: string;
  source: string;
}

export interface LevelCard {
  uroven: Level;
  krok: Step;
  kontakt: string | null;
  buttons: string[];
  sla_do: string | null;
}

export interface NavigatorReply {
  reply_text: string;
  lang: Lang;
  level_card: LevelCard | null;
  followup_question: string | null;
  facts: Fact[];
  cites: string[];
  escalated: boolean;
  triage: TriageOutput | null;
}

export interface ChatMessage {
  id: string;
  at: string;
  role: 'user' | 'navigator';
  author: string;
  text: string;
  level_card?: LevelCard | null;
  followup_question?: string | null;
}

export interface QuestionnaireOption {
  text: string;
  barva?: string | null;
  upozorneni?: string | null;
}

export type QuestionnaireDefinition = Record<string, unknown>;

export interface Contacts {
  monitoring_centre: { phone: string; hours: string };
  on_duty: { phone: string };
  ems: { phone: string };
}

export interface Health {
  iris: boolean;
  fhir: boolean;
  llm: boolean;
  mcp: boolean;
  version: string;
}

export interface DemoState {
  now: string;
  dataset: string;
}

export interface Kpi {
  today_by_level: Record<string, number>;
  open_tasks: number;
  sla_breached: number;
  missed_checkins: number;
  median_minutes_to_accept: number | null;
}

export interface DailyStat {
  date: string;
  by_level: Record<string, number>;
  checkins: number;
  missed: number;
}

export interface SymptomStat {
  symptom: string;
  patients: number;
  alerts: number;
  reports: number;
}

export interface SymptomPatient {
  patient_id: string;
  name: string;
  regimen: string;
  risk_badges: string[];
  max_grade: number;
  series: { date: string; grade: number }[];
}

export interface ReplayEvent {
  checkin_id: string;
  patient_id: string;
  at: string;
  output: TriageOutput;
  expected?: GroundTruth | null;
}

export interface EvalReport {
  metrics: Record<string, number | string | null>;
  confusion: number[][];
  errors: Record<string, unknown>[];
}
