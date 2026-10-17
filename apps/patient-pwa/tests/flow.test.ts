import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { buildFills, buildVitals, isUnknown, optionColor, phoneFacts, toggleOption, treatmentReason, UNKNOWN, visibleSteps, type Questionnaire } from '../src/flow.ts';
import { contactText, dictionaries } from '../src/i18n.ts';

const definitions: Questionnaire[] = JSON.parse(
  readFileSync(new URL('../../../data/rakathon_meddi_onco_data/docs/dotazniky_definice.json', import.meta.url), 'utf8'),
);
const nu = definitions.filter((questionnaire) => questionnaire.id === 'nezadouci_ucinky');
const ucinky = nu[0].otazky.find((item) => item.id === 'ucinky')!;

test('branching follows podminka, transitively', () => {
  assert.deepEqual(visibleSteps(nu, {}).map((step) => step.item.id), ['pocit', 'sobestacnost', 'ucinky']);
  const answers = { 'nezadouci_ucinky.ucinky': [1, 5], 'nezadouci_ucinky.stolice_typ': [0] };
  assert.deepEqual(visibleSteps(nu, answers).map((step) => step.item.id),
    ['pocit', 'sobestacnost', 'ucinky', 'stolice_typ', 'prujem', 'teplota']);
  const parentGone = { 'nezadouci_ucinky.ucinky': [5], 'nezadouci_ucinky.stolice_typ': [0] };
  assert.ok(!visibleSteps(nu, parentGone).some((step) => step.item.id === 'prujem'));
});

test('"no side effects" is exclusive', () => {
  assert.deepEqual(toggleOption(ucinky, [1, 5], 12), [12]);
  assert.deepEqual(toggleOption(ucinky, [12], 5), [5]);
  assert.deepEqual(toggleOption(ucinky, [5, 1], 5), [1]);
});

test('fills use the MEDDI check-in shape and drop hidden answers', () => {
  const answers = {
    'nezadouci_ucinky.pocit': 3,
    'nezadouci_ucinky.ucinky': [5],
    'nezadouci_ucinky.teplota': 1,
    'nezadouci_ucinky.prujem': 2,
  };
  const [fill] = buildFills(nu, answers, 'ONC-001-APP');
  assert.equal(fill.vyplneni_id, 'ONC-001-APP-NU');
  assert.deepEqual(fill.odpovedi.map((answer) => answer.otazka_id), ['pocit', 'ucinky', 'teplota']);
  assert.deepEqual(fill.odpovedi[0], {
    otazka_id: 'pocit', otazka: 'Jak se celkově cítíte?', odpoved: '4', odpoved_index: 3, barva: 'zelena', upozorneni: null,
  });
  assert.deepEqual(fill.odpovedi[1].odpoved, ['Zvýšená teplota a horečky']);
  assert.equal(fill.nejvyssi_barva, 'zluta');
  assert.equal(fill.zobrazena_upozorneni.length, 1);
});

test('"Nevím" is dropped like a skip; uncoloured options get a display colour', () => {
  const [fill] = buildFills(nu, { 'nezadouci_ucinky.pocit': UNKNOWN, 'nezadouci_ucinky.sobestacnost': 0 }, 'X');
  assert.deepEqual(fill.odpovedi.map((answer) => answer.otazka_id), ['sobestacnost']);
  const item = (id: string) => nu[0].otazky.find((question) => question.id === id)!;
  assert.deepEqual([0, 1, 2].map((index) => optionColor(item('kuze'), index)), ['zelena', 'zluta', 'cervena']);
  assert.equal(optionColor(item('pocit'), 4), 'cervena');
  assert.equal(optionColor(ucinky, 12), 'zelena');
  assert.equal(optionColor(ucinky, 3), 'zluta');
});

test('ESAS scales get the simplified colours', () => {
  const esas = definitions.filter((questionnaire) => questionnaire.id === 'esas');
  const [fill] = buildFills(esas, { 'esas.pohoda': 7, 'esas.bolest': 2 }, 'X');
  assert.deepEqual(fill.odpovedi.map((answer) => [answer.odpoved, answer.barva]), [[7, 'cervena'], [2, 'zelena']]);
  assert.equal(fill.nejvyssi_barva, 'cervena');
});

test('vitals accept a decimal comma and drop implausible values', () => {
  assert.deepEqual(buildVitals({ teplota_c: '38,4', tk_sys: '9999', spo2: '' }), {
    teplota_c: { hodnota: 38.4, zdroj: 'domaci_teplomer' },
  });
});

test('treatment reason names the drug from the regimen', () => {
  assert.deepEqual(treatmentReason('brneni', 'mFOLFOX6 à 14 dní'), { drug: 'FOLFOX' });
  assert.deepEqual(treatmentReason('teplota', 'AC (doxorubicin + cyklofosfamid)'), { chemo: true });
  assert.equal(treatmentReason('brneni', 'letrozol'), null);
});

test('a reopened red result reads the evidence aloud, not the raw vitals line', () => {
  const vital = { zdroj: 'vitalni_funkce', citace: 'teplota_c 38.4 (domaci_teplomer)' };
  const question = { zdroj: 'dotaznik', citace: 'Měl/a jste zvýšenou tělesnou teplotu nebo horečky? – 38,0 - 39,0°C méně než 24 hodin' };
  const dukazy = [
    vital,
    question,
    { zdroj: 'zprava', citace: 'naměřila jsem 38,4' },
    { zdroj: 'zprava', citace: 'Od odpoledne mi je zima a třese mě, naměřila jsem 38,4' },
    { zdroj: 'zprava', citace: 'Od odpoledne mi je zima a třese mě' },
  ];
  assert.deepEqual(phoneFacts(dukazy), {
    vitals: { teplota_c: { hodnota: 38.4 } },
    words: 'Od odpoledne mi je zima a třese mě, naměřila jsem 38,4',
  });
  assert.deepEqual(phoneFacts([vital, question]).words, question.citace);
  const checkin = { patient_id: 'ONC-001', stav: 'vyplneno', vyplnil: 'pacient', dotazniky: [], zprava_pacienta: 'Je mi zima.', vitalni_funkce: { spo2: { hodnota: 91, zdroj: 'oxymetr' } } } as const;
  assert.deepEqual(phoneFacts(dukazy, checkin), { vitals: checkin.vitalni_funkce, words: 'Je mi zima.' });
  assert.equal(phoneFacts([vital], { ...checkin, zprava_pacienta: null }).words, '');
});

test('Slovak cards show every backend contact line in Slovak', () => {
  const router = readFileSync(new URL('../../../backend/app/triage/router.py', import.meta.url), 'utf8');
  const contacts = [...router.matchAll(/^CONTACT_\w+ = "(.+)"$/gm)].map((match) => match[1]);
  assert.equal(contacts.length, 6);
  for (const contact of contacts) {
    assert.equal(contactText(contact, 'cs'), contact);
    assert.notEqual(contactText(contact, 'sk'), contact, contact);
  }
  assert.equal(contactText('monitorovací centrum – následující pracovní den', 'sk'), 'monitorovacie centrum – nasledujúci pracovný deň');
  assert.equal(contactText('sloužící lékař MOÚ 724 590 848 – ihned', 'sk'), 'službukonajúci lekár MOÚ 724 590 848 – ihneď');
  assert.equal(contactText('neznámý kontakt', 'sk'), 'neznámý kontakt');
});

test('the breaths-per-minute label is short enough for the two-column vitals grid', () => {
  assert.equal(dictionaries.cs.vital_dechova_frekvence, 'Počet dechů');
  assert.equal(dictionaries.sk.vital_dechova_frekvence, 'Počet dychov');
  const longest = (lang: 'cs' | 'sk') => Math.max(...Object.entries(dictionaries[lang]).filter(([key]) => key.startsWith('vital_')).map(([, label]) => label.length));
  assert.ok(longest('cs') <= 13 && longest('sk') <= 13);
});

test('an untouched single-choice question counts as „Nevím“, so the AI hint shows right away', () => {
  assert.ok(isUnknown(undefined));
  assert.ok(isUnknown(UNKNOWN));
  assert.equal(isUnknown(0), false);
});
