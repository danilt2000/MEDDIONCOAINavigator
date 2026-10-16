import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { buildFills, buildVitals, toggleOption, treatmentReason, visibleSteps, type Questionnaire } from '../src/flow.ts';

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
