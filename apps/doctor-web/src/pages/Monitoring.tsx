import type { DailyStat, QueueItem, SymptomStat } from '@navigator/api';
import { OutlinedCard, OutlinedTextField, SvgIcon } from '@navigator/ui';
import { useMemo, useState, type CSSProperties } from 'react';
import { Link, useNavigate } from 'react-router';
import { Area, AreaChart, Brush, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useShell } from '../App';
import { Load } from '../components';
import { warningIcon } from '../icons';
import { fmtDay, shortRegimen, useApi, type Loadable } from '../lib';

const dayHref = (date: string) => `/monitoring/den/${date}`;
const symptomHref = (symptom: string) => `/monitoring/priznak/${encodeURIComponent(symptom)}`;
const regimenHref = (regimen: string) => `/monitoring/lecba/${encodeURIComponent(regimen)}`;

export function MonitoringPage() {
  const { range } = useShell();
  const navigate = useNavigate();
  const daily = useApi<DailyStat[]>(`/api/stats/daily?from=${range.from}&to=${range.to}`, 30000);
  const symptoms = useApi<SymptomStat[]>(`/api/stats/symptoms?from=${range.from}&to=${range.to}`, 30000);
  const tasks = useApi<QueueItem[]>('/api/queue?status=all', 30000);

  const openDay = (state: { activeLabel?: string | number }) => {
    if (state.activeLabel) navigate(dayHref(String(state.activeLabel)));
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Monitoring</h1>
          <p className="muted">
            {fmtDay(range.from)} – {fmtDay(range.to)} · kliknutím na den, léčbu nebo příznak zobrazíte pacienty
          </p>
        </div>
      </div>

      <div className="board">
        <div className="board-main">
          <Load source={daily} isEmpty={(rows) => rows.length === 0} emptyText="V období nejsou žádné check-iny.">
            {(rows) => <ActivityCard key={range.from} rows={rows} onOpenDay={openDay} />}
          </Load>

          <OutlinedCard className="card">
            <SymptomTable source={symptoms} onOpen={(symptom) => navigate(symptomHref(symptom))} />
          </OutlinedCard>
        </div>

        <aside className="board-side">
          <OutlinedCard className="card">
            <h2 className="section-title">Upozornění podle léčby</h2>
            <p className="muted small">Klikněte na léčbu a uvidíte, proč pacienti upozornění dostali.</p>
            <Load source={tasks} isEmpty={(items) => items.length === 0} emptyText="Žádné úkoly v období.">
              {(items) => <RegimenTable items={items.filter((item) => item.created.slice(0, 10) >= range.from)} />}
            </Load>
          </OutlinedCard>
        </aside>
      </div>
    </div>
  );
}

const alertsOf = (row: DailyStat) => (row.by_level['2'] ?? 0) + (row.by_level['3'] ?? 0) + (row.by_level['4'] ?? 0);

type TipProps = { active?: boolean; payload?: readonly { value?: unknown; dataKey?: unknown }[]; label?: string | number };

const alertTip = ({ active, payload, label }: TipProps) =>
  active && payload?.length ? (
    <div className="chart-tip">
      {fmtDay(String(label))} · <strong>{String(payload[0].value)}</strong> upozornění
    </div>
  ) : null;

const questionnaireTip = ({ active, payload, label }: TipProps) => {
  if (!active || !payload?.length) return null;
  const value = (key: string) => String(payload.find((entry) => entry.dataKey === key)?.value ?? 0);
  return (
    <div className="chart-tip">
      {fmtDay(String(label))} · <strong>{value('checkins')}</strong> vyplněno · <strong>{value('missed')}</strong> nevyplněno
    </div>
  );
};

function ActivityCard({ rows, onOpenDay }: { rows: DailyStat[]; onOpenDay: (state: { activeLabel?: string | number }) => void }) {
  const [span, setSpan] = useState({ startIndex: 0, endIndex: rows.length - 1 });
  const data = useMemo(() => rows.map((row) => ({ date: row.date, alerts: alertsOf(row), checkins: row.checkins, missed: row.missed })), [rows]);
  const visible = data.slice(span.startIndex, span.endIndex + 1);
  const grid = <CartesianGrid vertical={false} stroke="var(--md-sys-color-outline-variant)" />;
  const yAxis = <YAxis allowDecimals={false} width={32} tick={{ fontSize: 12 }} />;

  return (
    <OutlinedCard className="card">
      <div className="row space">
        <h2 className="section-title row gap-4">
          <SvgIcon svg={warningIcon} className="alert-title-icon" />
          Upozornění (stupeň 2–4)
        </h2>
        <span className="muted">
          celkem <strong>{visible.reduce((sum, row) => sum + row.alerts, 0)}</strong>
        </span>
      </div>
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={visible} onClick={onOpenDay} style={{ cursor: 'pointer' }}>
          {grid}
          <XAxis dataKey="date" hide />
          {yAxis}
          <Tooltip content={alertTip} />
          <Area isAnimationActive={false} type="linear" dataKey="alerts" stroke="var(--chart-4)" fill="var(--chart-4)" fillOpacity={0.16} />
        </AreaChart>
      </ResponsiveContainer>
      <h2 className="section-title">Dotazníky</h2>
      <ResponsiveContainer width="100%" height={170}>
        <AreaChart data={visible} onClick={onOpenDay} style={{ cursor: 'pointer' }}>
          {grid}
          <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fontSize: 12 }} />
          {yAxis}
          <Tooltip content={questionnaireTip} />
          <Area
            isAnimationActive={false}
            type="linear"
            dataKey="checkins"
            stroke="var(--md-sys-color-primary)"
            fill="var(--md-sys-color-primary)"
            fillOpacity={0.14}
          />
          <Area
            isAnimationActive={false}
            type="linear"
            dataKey="missed"
            stroke="var(--md-sys-color-outline)"
            strokeDasharray="4 3"
            fill="var(--md-sys-color-outline)"
            fillOpacity={0.08}
          />
        </AreaChart>
      </ResponsiveContainer>
      <ResponsiveContainer width="100%" height={36}>
        <AreaChart data={data} margin={{ top: 4, right: 5, bottom: 4, left: 37 }}>
          <XAxis dataKey="date" hide />
          <Brush
            dataKey="date"
            height={28}
            travellerWidth={10}
            tickFormatter={fmtDay}
            stroke="var(--md-sys-color-primary)"
            fill="var(--md-sys-color-surface-container-lowest)"
            onChange={(next) => setSpan({ startIndex: next.startIndex ?? 0, endIndex: next.endIndex ?? rows.length - 1 })}
          />
        </AreaChart>
      </ResponsiveContainer>
      <p className="muted small range-labels">
        <span>{fmtDay(visible[0].date)}</span>
        <span>{fmtDay(visible[visible.length - 1].date)}</span>
      </p>
      <p className="muted small">Kliknutím do grafu uvidíte pacienty se stupněm 2 a výš v daný den. Posuvníkem dole zúžíte období.</p>
    </OutlinedCard>
  );
}

function SymptomTable({ source, onOpen }: { source: Loadable<SymptomStat[]>; onOpen: (symptom: string) => void }) {
  const [query, setQuery] = useState('');
  return (
    <>
      <div className="row space">
        <h2 className="section-title">Příznaky z dotazníků a chatu</h2>
        <OutlinedTextField
          className="search"
          type="search"
          label="Hledat příznak"
          value={query}
          onInput={(event) => setQuery((event.target as HTMLInputElement).value)}
        />
      </div>
      <Load source={source} isEmpty={(rows) => rows.length === 0} emptyText="V období nikdo nehlásil příznaky.">
        {(rows) => {
          const maxAlerts = Math.max(1, ...rows.map((row) => row.alerts));
          const maxReports = Math.max(1, ...rows.map((row) => row.reports));
          const visible = rows
            .filter((row) => row.symptom.toLowerCase().includes(query.trim().toLowerCase()))
            .sort((left, right) => right.alerts - left.alerts || right.reports - left.reports);
          return (
            <table className="table symptom-table">
              <thead>
                <tr>
                  <th>Příznak</th>
                  <th>Pacienti</th>
                  <th aria-sort="descending">Upozornění ↓</th>
                  <th>Hlášení celkem</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.symptom} className="clickable" onClick={() => onOpen(row.symptom)}>
                    <th scope="row">
                      <button type="button" className="link-button" onClick={() => onOpen(row.symptom)}>
                        {row.symptom}
                      </button>
                    </th>
                    <td>{row.patients}</td>
                    <td className="bar-cell">
                      <span className="bar bar-alert" style={{ '--ratio': row.alerts / maxAlerts } as CSSProperties} />
                      <span className="bar-value">{row.alerts}</span>
                    </td>
                    <td className="bar-cell">
                      <span className="bar bar-report" style={{ '--ratio': row.reports / maxReports } as CSSProperties} />
                      <span className="bar-value">{row.reports}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }}
      </Load>
    </>
  );
}

function RegimenTable({ items }: { items: QueueItem[] }) {
  const navigate = useNavigate();
  const byRegimen = new Map<string, { alerts: number; patients: Set<string> }>();
  items.forEach((item) => {
    const regimen = shortRegimen(item.regimen);
    const row = byRegimen.get(regimen) ?? { alerts: 0, patients: new Set<string>() };
    row.alerts += 1;
    row.patients.add(item.patient_id);
    byRegimen.set(regimen, row);
  });
  const rows = [...byRegimen].sort((left, right) => right[1].alerts - left[1].alerts).slice(0, 10);
  if (!rows.length) return <p className="muted">Žádná upozornění v období.</p>;
  const max = rows[0][1].alerts;
  return (
    <table className="table compact regimen-table">
      <colgroup>
        <col />
        <col className="col-patients" />
        <col className="col-bar" />
        <col className="col-count" />
      </colgroup>
      <thead>
        <tr>
          <th>Léčba</th>
          <th>Pacienti</th>
          <th colSpan={2} aria-sort="descending">
            Upozornění ↓
          </th>
        </tr>
      </thead>
      <tbody>
        <tr className="total-row">
          <th scope="row">Celkem</th>
          <td>{new Set(items.map((item) => item.patient_id)).size}</td>
          <td />
          <td className="count-cell">{items.length}</td>
        </tr>
        {rows.map(([regimen, row]) => (
          <tr key={regimen} className="clickable" onClick={() => navigate(regimenHref(regimen))}>
            <th scope="row" className="ellipsis-cell" title={regimen}>
              <Link to={regimenHref(regimen)} onClick={(event) => event.stopPropagation()}>
                {regimen}
              </Link>
            </th>
            <td>{row.patients.size}</td>
            <td className="regimen-bar">
              <span className="bar bar-alert-strong" style={{ width: `${(row.alerts / max) * 100}%` }} />
            </td>
            <td className="count-cell">
              <Link to={regimenHref(regimen)} onClick={(event) => event.stopPropagation()}>
                {row.alerts}
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
