import type { Answer, CheckinInput, Evidence, Measurement, QuestionnaireFill } from '@navigator/api';

export interface Option {
  text: string;
  barva?: string | null;
  upozorneni?: string | null;
}

export interface Item {
  id: string;
  text: string;
  navod?: string;
  typ: 'jedna' | 'vice' | 'text' | 'skala_1_10' | 'cislo';
  moznosti?: Option[];
  podminka?: string;
}

export interface Questionnaire {
  id: string;
  nazev: string;
  otazky: Item[];
}

export type Value = number | number[] | string;
export type Answers = Record<string, Value>;

export interface Step {
  questionnaire: Questionnaire;
  item: Item;
}

export const answerKey = (questionnaireId: string, itemId: string) => `${questionnaireId}.${itemId}`;

export function visibleSteps(questionnaires: Questionnaire[], answers: Answers): Step[] {
  const steps: Step[] = [];
  for (const questionnaire of questionnaires) {
    const shown = new Set<string>();
    for (const item of questionnaire.otazky) {
      if (item.podminka) {
        const [parentId, index] = item.podminka.split(':');
        if (!shown.has(parentId)) continue;
        const parentValue = answers[answerKey(questionnaire.id, parentId)];
        const hit = Array.isArray(parentValue) ? parentValue.includes(Number(index)) : parentValue === Number(index);
        if (!hit) continue;
      }
      shown.add(item.id);
      steps.push({ questionnaire, item });
    }
  }
  return steps;
}

const isExclusive = (option: Option) => option.text.startsWith('Nemám žádné');

export function toggleOption(item: Item, current: number[], index: number): number[] {
  const options = item.moznosti ?? [];
  if (current.includes(index)) return current.filter((selected) => selected !== index);
  if (isExclusive(options[index])) return [index];
  return [...current.filter((selected) => !isExclusive(options[selected])), index].sort((a, b) => a - b);
}

// "Nevím, jak odpovědět": the default of every single-choice question, stored like a skipped answer.
export const UNKNOWN = -1;
export const isUnknown = (value: Value | undefined) => value === undefined || value === UNKNOWN;

export const hasValue = (value: Value | undefined) =>
  value !== undefined && value !== UNKNOWN && value !== '' && !(Array.isArray(value) && value.length === 0);

const esasColor = (score: number) => (score <= 3 ? 'zelena' : score <= 5 ? 'zluta' : 'cervena');
// Display only: MEDDI leaves these options uncoloured, so they follow its own similar questions
// (bol_klouby = bol_bricho, kuze = afty). The barva sent to the backend stays MEDDI's.
const DERIVED_COLORS: Record<string, string[]> = {
  bol_klouby: ['zelena', 'zelena', 'zluta'],
  kuze: ['zelena', 'zluta', 'cervena'],
  spokojenost: ['zelena', 'zluta'],
};

export function optionColor(item: Item, index: number): string | null {
  const option = item.moznosti?.[index];
  if (!option) return null;
  if (option.barva) return option.barva;
  if (item.typ === 'vice') return isExclusive(option) ? 'zelena' : 'zluta';
  return DERIVED_COLORS[item.id]?.[index] ?? null;
}

export const scaleColor = (questionnaireId: string, itemId: string, score: number) =>
  questionnaireId === 'esas' || itemId === 'nrs' ? esasColor(score) : null;
const COLOR_RANK: Record<string, number> = { zelena: 1, zluta: 2, cervena: 3 };

function toAnswer(questionnaireId: string, item: Item, value: Value): Answer {
  const base = { otazka_id: item.id, otazka: item.text, barva: null, upozorneni: null };
  const options = item.moznosti ?? [];
  if (item.typ === 'jedna') {
    const option = options[value as number];
    return {
      ...base,
      odpoved: option.text,
      odpoved_index: value as number,
      barva: option.barva ?? null,
      upozorneni: option.upozorneni ?? null,
    };
  }
  if (item.typ === 'vice') {
    const indices = value as number[];
    return { ...base, odpoved: indices.map((index) => options[index].text), odpoved_index: indices };
  }
  if (item.typ === 'skala_1_10') {
    return { ...base, odpoved: value as number, odpoved_index: null, barva: questionnaireId === 'esas' ? esasColor(value as number) : null };
  }
  return { ...base, odpoved: typeof value === 'string' ? value.trim() : (value as number), odpoved_index: null };
}

export function buildFills(questionnaires: Questionnaire[], answers: Answers, idPrefix: string): QuestionnaireFill[] {
  const steps = visibleSteps(questionnaires, answers);
  const suffix: Record<string, string> = {
    nezadouci_ucinky: 'NU',
    psychoonkologicky_screening: 'PSY',
    bolest_analgeticka_terapie: 'ANALG',
    esas: 'ESAS',
  };
  return questionnaires
    .map((questionnaire) => {
      const odpovedi = steps
        .filter((step) => step.questionnaire === questionnaire)
        .filter((step) => hasValue(answers[answerKey(questionnaire.id, step.item.id)]))
        .map((step) => toAnswer(questionnaire.id, step.item, answers[answerKey(questionnaire.id, step.item.id)]));
      const colors = odpovedi.map((answer) => answer.barva).filter((color): color is string => !!color);
      const highest = colors.sort((a, b) => (COLOR_RANK[b] ?? 0) - (COLOR_RANK[a] ?? 0))[0] ?? null;
      const warnings = [...new Set(odpovedi.map((answer) => answer.upozorneni).filter((text): text is string => !!text))];
      return {
        vyplneni_id: `${idPrefix}-${suffix[questionnaire.id] ?? questionnaire.id}`,
        dotaznik_id: questionnaire.id,
        dotaznik_nazev: questionnaire.nazev,
        odpovedi,
        nejvyssi_barva: highest,
        zobrazena_upozorneni: warnings,
      };
    })
    .filter((fill) => fill.odpovedi.length > 0);
}

export const VITALS = [
  { key: 'teplota_c', zdroj: 'domaci_teplomer', unit: '°C', min: 34, max: 43 },
  { key: 'tk_sys', zdroj: 'domaci_tlakomer', unit: 'mmHg', min: 50, max: 260 },
  { key: 'tk_dia', zdroj: 'domaci_tlakomer', unit: 'mmHg', min: 30, max: 160 },
  { key: 'tepova_frekvence', zdroj: 'domaci_tlakomer', unit: '/min', min: 25, max: 230 },
  { key: 'dechova_frekvence', zdroj: 'spocitano_doma', unit: '/min', min: 4, max: 60 },
  { key: 'spo2', zdroj: 'oxymetr', unit: '%', min: 50, max: 100 },
  { key: 'vaha_kg', zdroj: 'domaci_vaha', unit: 'kg', min: 25, max: 250 },
  { key: 'glykemie_mmol_l', zdroj: 'glukometr', unit: 'mmol/l', min: 1, max: 40 },
] as const;

export type VitalKey = (typeof VITALS)[number]['key'];

export function parseVital(key: VitalKey, raw: string): number | null | 'invalid' {
  const text = raw.trim().replace(',', '.');
  if (!text) return null;
  const value = Number(text);
  const spec = VITALS.find((vital) => vital.key === key)!;
  return Number.isFinite(value) && value >= spec.min && value <= spec.max ? value : 'invalid';
}

export function buildVitals(raw: Partial<Record<VitalKey, string>>): Record<string, Measurement> {
  const vitals: Record<string, Measurement> = {};
  for (const vital of VITALS) {
    const value = parseVital(vital.key, raw[vital.key] ?? '');
    if (typeof value === 'number') vitals[vital.key] = { hodnota: value, zdroj: vital.zdroj };
  }
  return vitals;
}

const OWN_WORDS = ['zprava', 'priloha', 'chat'];

// A reopened result has no check-in, only its evidence: vitals come back from "teplota_c 38.4 (domaci_teplomer)",
// the words from the patient's own quotes (else the questionnaire answers), never from the raw vitals line.
export function phoneFacts(dukazy: Evidence[], checkin?: CheckinInput) {
  const measured: Record<string, { hodnota: number }> = {};
  for (const evidence of dukazy) {
    const [key, value] = evidence.citace.split(' ');
    if (evidence.zdroj === 'vitalni_funkce' && Number.isFinite(Number(value))) measured[key] = { hodnota: Number(value) };
  }
  const own = dukazy.filter((evidence) => OWN_WORDS.includes(evidence.zdroj));
  const quotes = [...new Set((own.length ? own : dukazy.filter((evidence) => evidence.zdroj === 'dotaznik')).map((evidence) => evidence.citace))];
  const words = quotes.filter((quote) => !quotes.some((other) => other !== quote && other.includes(quote))).slice(0, 2).join('; ');
  return { vitals: checkin?.vitalni_funkce ?? measured, words: checkin?.zprava_pacienta || words };
}

const CYTOTOXIC = ['doxorubicin', 'cyklofosfamid', 'oxaliplatin', 'folfox', 'folfiri', 'irinotekan', 'karboplatin',
  'etoposid', 'cisplatin', 'kapecitabin', 'vinkristin', 'paklitaxel', 'r-chop', '5-fu', 'fluorouracil'];
const IMMUNO = ['ipilimumab', 'nivolumab', 'atezolizumab', 'pembrolizumab'];

const REASONS: { items: string[]; drugs: string[]; label?: 'chemo' }[] = [
  { items: ['brneni'], drugs: ['oxaliplatin', 'folfox', 'vinkristin', 'r-chop', 'paklitaxel', 'cisplatin'] },
  { items: ['stolice_typ', 'prujem'], drugs: ['irinotekan', 'folfiri', 'kapecitabin', 'folfox', '5-fu', ...IMMUNO] },
  { items: ['teplota'], drugs: CYTOTOXIC, label: 'chemo' },
  { items: ['krvaceni'], drugs: ['warfarin', 'bevacizumab', 'sunitinib'] },
  { items: ['dusnost'], drugs: [...IMMUNO, 'trastuzumab'] },
  { items: ['kuze'], drugs: ['kapecitabin', ...IMMUNO] },
  { items: ['nnz_typ', 'nevolnost', 'zvraceni'], drugs: ['cisplatin', 'karboplatin', 'doxorubicin', 'cyklofosfamid', 'irinotekan'] },
];

export function treatmentReason(itemId: string, treatmentText: string): { drug: string } | { chemo: true } | null {
  const lower = treatmentText.toLowerCase();
  for (const reason of REASONS) {
    if (!reason.items.includes(itemId)) continue;
    const drug = reason.drugs.find((name) => lower.includes(name));
    if (!drug) continue;
    if (reason.label === 'chemo') return { chemo: true };
    const start = lower.indexOf(drug);
    return { drug: treatmentText.slice(start, start + drug.length) };
  }
  return null;
}
