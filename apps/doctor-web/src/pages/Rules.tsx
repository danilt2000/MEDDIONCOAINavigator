import { OutlinedCard, TriageChip } from '@navigator/ui';

const RED: [string, string][] = [
  ['R-FEVER', 'Teplota ≥ 38,0 °C nebo zimnice během chemoterapie nebo do 6 týdnů po ní'],
  ['R-BREATH', 'Dušnost v klidu; SpO2 < 90 %; náhlá dušnost s bolestí na hrudi nebo bušením srdce'],
  ['R-CHEST', 'Nová bolest na hrudi'],
  ['R-NEURO', 'Zmatenost, porucha vědomí, křeče, nová slabost končetin, porucha řeči'],
  ['R-BLEED', 'Krev ve stolici nebo zvratcích, černá stolice, krev v moči, krvácení z nosu > 20 min, úraz hlavy na antikoagulaci'],
  ['R-DIARRHEA', '≥ 7 stolic nad normál za 24 h nebo průjem s krví'],
  ['R-VOMIT', '> 5 zvracení za 24 h nebo neudrží tekutiny se známkami dehydratace'],
  ['R-DEHYD', 'Nemočí > 10 h, mdloba, systolický tlak < 90 mmHg'],
  ['R-ILEUS', 'Bez stolice a plynů se zvracením nebo kolikovitou bolestí'],
  ['R-BP', 'TK ≥ 180/110 nebo vysoký tlak se silnou bolestí hlavy, poruchou zraku či řeči, bolestí na hrudi'],
  ['R-DKA', 'Zvracení + bolest břicha + zrychlený dech u diabetika nebo na imunoterapii'],
  ['R-OPIOID', 'Nová výrazná ospalost, nereagování nebo zpomalený dech na opioidech'],
  ['R-SUICIDE', 'Sebevražedné myšlenky s plánem, úmyslem nebo prostředky'],
];

const ORANGE: [string, string][] = [
  ['O-GENERAL', '„Jak se celkově cítíte?“ = 5 (velmi špatně)'],
  ['O-BREATH', 'SpO2 < 92 % nebo pokles o ≥ 3 body; nově spí vsedě / na více polštářích'],
  ['O-DIARRHEA-RISK', '4–6 stolic nad normál na imunoterapii, fluoropyrimidinech nebo irinotekanu; průjem nereagující na loperamid'],
  ['O-IO-DIARRHEA-PAIN', 'Jakýkoli průjem s bolestí břicha na imunoterapii'],
  ['O-INTAKE', 'Neudrží tekutiny; nově jen tekutiny s nezvládnutou bolestí; málo moči nebo závratě při nízkém příjmu'],
  ['O-VOMIT', '3–5 zvracení za 24 h a neudrží tekutiny'],
  ['O-BP-ANTIANGIO', 'TK ≥ 160/100 na antiangiogenní léčbě'],
  ['O-BLEED-ANTICOAG', 'Jakékoli krvácení nebo nové modřiny na antikoagulaci'],
  ['O-DVT', 'Jednostranný otok a bolest lýtka'],
  ['O-PAIN', 'Bolest NRS ≥ 7 neustupující po záchranné (SOS) dávce'],
  ['O-BRAIN', 'Ranní bolest hlavy se zvracením u mozkového nádoru'],
  ['O-IO-ENDO', 'Silná žízeň, časté močení a hubnutí na imunoterapii'],
  ['O-HYPO', 'Glykémie < 4 mmol/l na inzulinu'],
  ['O-PSYCH', 'Pasivní přání smrti („nejraději bych si vzal/a život“) nebo beznaděj'],
  ['O-REPEAT', 'Zhoršení, přestože je vyšetření už naplánované – nečekat na termín'],
];

const ROUTING: [1 | 2 | 3 | 4, string, string, string][] = [
  [1, '— (tým vidí v přehledu)', '—', '—'],
  [2, 'monitorovací centrum – vyřízení do konce následujícího pracovního dne', 'monitorovací centrum – následující pracovní den', 'konec dalšího pracovního dne'],
  [3, 'telekonzultace s lékařem přes monitorovací centrum do 2 h', 'sloužící lékař 724 590 848 – ihned', '2 h / ihned'],
  [4, '155 / urgentní příjem', '155 / urgentní příjem (případně sloužící lékař 724 590 848)', 'tým upozorněn do 15 min'],
];

function RuleTable({ rules }: { rules: [string, string][] }) {
  return (
    <table className="table compact">
      <tbody>
        {rules.map(([id, text]) => (
          <tr key={id}>
            <th scope="row">
              <code className="rule-chip">{id}</code>
            </th>
            <td>{text}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function RulesPage() {
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Pravidla</h1>
          <p className="muted">
            Stupeň počítá deterministický engine jako maximum z tvrdých pravidel, kontextu léčby, trendů, chybějících check-inů a rozporů. AI jen
            čte volný text a formuluje odpověď – stupeň nikdy nenastavuje ani nesnižuje.
          </p>
        </div>
      </div>
      <OutlinedCard className="card">
        <h2 className="section-title">Směrování podle pracovní doby (Po–Pá 7:00–15:30, Europe/Prague)</h2>
        <table className="table">
          <thead>
            <tr>
              <th>Stupeň</th>
              <th>V pracovní době</th>
              <th>Mimo pracovní dobu</th>
              <th>SLA</th>
            </tr>
          </thead>
          <tbody>
            {ROUTING.map(([level, inside, outside, sla]) => (
              <tr key={level}>
                <td>
                  <TriageChip level={level} withStep />
                </td>
                <td>{inside}</td>
                <td>{outside}</td>
                <td>{sla}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </OutlinedCard>
      <div className="two-col">
        <OutlinedCard className="card">
          <h2 className="section-title row gap-4">
            <TriageChip level={4} /> Tvrdá pravidla – minimálně stupeň 4
          </h2>
          <RuleTable rules={RED} />
        </OutlinedCard>
        <OutlinedCard className="card">
          <h2 className="section-title row gap-4">
            <TriageChip level={3} /> Tvrdá pravidla – minimálně stupeň 3
          </h2>
          <RuleTable rules={ORANGE} />
        </OutlinedCard>
      </div>
      <OutlinedCard className="card">
        <h2 className="section-title">Bezpečnostní zásady</h2>
        <ul className="tight">
          <li>Systém pacientovi nikdy nesděluje diagnózu a nikdy nemění ani nepočítá dávky – cituje jen předem dohodnuté pokyny z jeho léků.</li>
          <li>Stupně 2–4 vždy končí u zdravotníka; stupeň 4 = volat ihned 155 nebo sloužícího lékaře.</li>
          <li>Při nejistotě platí vyšší stupeň a pacient dostane doplňující otázku.</li>
          <li>Zpráva pacienta má přednost před dotazníkem; rozpor se zapíše do klíčových nálezů.</li>
          <li>Předem vyslovená přání jsou informace pro tým, nikdy důvod nedoporučit pomoc.</li>
          <li>Typicky žlutá (stupeň 2): příznak stupně 2 bez varovných známek, zhoršující se trend, vynechané léky, psychická zátěž, 3 vynechané check-iny za sebou.</li>
        </ul>
      </OutlinedCard>
    </div>
  );
}
