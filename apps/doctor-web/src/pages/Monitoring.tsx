import type { DailyStat, Kpi as KpiData, QueueItem, SymptomStat } from '@navigator/api';
import { FilledTonalButton, OutlinedCard, OutlinedTextField, SvgIcon, TriageChip } from '@navigator/ui';
import { useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useShell } from '../App';
import { Kpi, Load } from '../components';
import { trendingUpIcon } from '../icons';
import { addDays, fmtDay, shortRegimen, useApi, type Loadable } from '../lib';

export const LEVEL_SERIES = [
  { key: '1', name: 'Zelená', color: 'var(--chart-1)' },
  { key: '2', name: 'Žlutá', color: 'var(--chart-2)' },
  { key: '3', name: 'Oranžová', color: 'var(--chart-3)' },
  { key: '4', name: 'Červená', color: 'var(--chart-4)' },
];

const dayHref = (date: string) => `/monitoring/den/${date}`;
const symptomHref = (symptom: string) => `/monitoring/priznak/${encodeURIComponent(symptom)}`;

export function MonitoringPage() {
  const { range } = useShell();
  const navigate = useNavigate();
  const kpi = useApi<KpiData>('/api/stats/kpi', 10000);
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
            {fmtDay(range.from)} – {fmtDay(range.to)} · kliknutím na den nebo příznak zobrazíte pacienty
          </p>
        </div>
      </div>

      <Load source={kpi}>
        {(data) => (
          <div className="kpi-row">
            <div className="kpi">
              <span className="kpi-label">Dnes podle stupně</span>
              <span className="row wrap">
                {LEVEL_SERIES.map((level) => (
                  <span key={level.key} className="row gap-4">
                    <TriageChip level={Number(level.key) as 1 | 2 | 3 | 4} />
                    <strong className="kpi-small">{data.today_by_level[level.key] ?? 0}</strong>
                  </span>
                ))}
              </span>
            </div>
            <Kpi label="Otevřené úkoly" value={data.open_tasks} />
            <Kpi label="SLA překročeno" value={data.sla_breached} tone={data.sla_breached > 0 ? 'alert' : 'ok'} />
            <Kpi label="Vynechané check-iny" value={data.missed_checkins} />
            <Kpi
              label="Čas do převzetí, medián"
              value={data.median_minutes_to_accept == null ? '—' : `${Math.round(data.median_minutes_to_accept)} min`}
            />
          </div>
        )}
      </Load>

      <div className="board">
        <div className="board-main">
          <OutlinedCard className="card">
            <h2 className="section-title">Check-iny podle stupně po dnech</h2>
            <Load source={daily} isEmpty={(rows) => rows.length === 0} emptyText="V období nejsou žádné check-iny.">
              {(rows) => (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={rows.map(flattenDay)} onClick={openDay} style={{ cursor: 'pointer' }}>
                    <CartesianGrid vertical={false} stroke="var(--md-sys-color-outline-variant)" />
                    <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} width={32} tick={{ fontSize: 12 }} />
                    <Tooltip labelFormatter={(label) => fmtDay(String(label))} />
                    <Legend itemSorter="dataKey" />
                    {LEVEL_SERIES.map((level) => (
                      <Bar isAnimationActive={false} key={level.key} dataKey={`l${level.key}`} name={level.name} stackId="levels" fill={level.color} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Load>
          </OutlinedCard>

          <OutlinedCard className="card">
            <div className="row space">
              <h2 className="section-title">Upozornění (stupeň 2–4) po dnech</h2>
              {daily.data && (
                <span className="muted">
                  celkem <strong>{daily.data.reduce((sum, row) => sum + alertsOf(row), 0)}</strong>
                </span>
              )}
            </div>
            <Load source={daily} isEmpty={(rows) => rows.length === 0} emptyText="V období nejsou žádná upozornění.">
              {(rows) => (
                <ResponsiveContainer width="100%" height={160}>
                  <AreaChart data={rows.map((row) => ({ date: row.date, alerts: alertsOf(row) }))} onClick={openDay} style={{ cursor: 'pointer' }}>
                    <CartesianGrid vertical={false} stroke="var(--md-sys-color-outline-variant)" />
                    <XAxis dataKey="date" tickFormatter={fmtDay} tick={{ fontSize: 12 }} />
                    <YAxis allowDecimals={false} width={32} tick={{ fontSize: 12 }} />
                    <Tooltip labelFormatter={(label) => fmtDay(String(label))} />
                    <Area isAnimationActive={false} type="linear" dataKey="alerts" name="Upozornění" stroke="var(--chart-4)" fill="var(--chart-4)" fillOpacity={0.16} />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </Load>
            <p className="muted small">Klikněte do grafu a uvidíte pacienty se stupněm 2 a výš v daný den.</p>
          </OutlinedCard>

          <OutlinedCard className="card">
            <SymptomTable source={symptoms} onOpen={(symptom) => navigate(symptomHref(symptom))} />
          </OutlinedCard>
        </div>

        <aside className="board-side">
          <OutlinedCard className="card">
            <h2 className="section-title">Upozornění podle léčby</h2>
            <Load source={tasks} isEmpty={(items) => items.length === 0} emptyText="Žádné úkoly v období.">
              {(items) => <RegimenBars items={items.filter((item) => item.created.slice(0, 10) >= range.from)} />}
            </Load>
          </OutlinedCard>
          <TrendCard to={range.to} />
        </aside>
      </div>
    </div>
  );
}

const alertsOf = (row: DailyStat) => (row.by_level['2'] ?? 0) + (row.by_level['3'] ?? 0) + (row.by_level['4'] ?? 0);

function flattenDay(row: DailyStat) {
  return {
    date: row.date,
    l1: row.by_level['1'] ?? 0,
    l2: row.by_level['2'] ?? 0,
    l3: row.by_level['3'] ?? 0,
    l4: row.by_level['4'] ?? 0,
  };
}

function SymptomTable({ source, onOpen }: { source: Loadable<SymptomStat[]>; onOpen: (symptom: string) => void }) {
  const [query, setQuery] = useState('');
  return (
    <>
      <div className="row space">
        <h2 className="section-title">Příznaky z dotazníku MEDDI</h2>
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

function RegimenBars({ items }: { items: QueueItem[] }) {
  const counts = new Map<string, number>();
  items.forEach((item) => counts.set(shortRegimen(item.regimen), (counts.get(shortRegimen(item.regimen)) ?? 0) + 1));
  const rows = [...counts].sort((left, right) => right[1] - left[1]).slice(0, 8);
  const max = Math.max(1, ...rows.map(([, count]) => count));
  if (!rows.length) return <p className="muted">Žádná upozornění v období.</p>;
  return (
    <div className="regimen-bars">
      {rows.map(([regimen, count]) => (
        <div key={regimen} className="regimen-row">
          <span className="ellipsis" title={regimen}>
            {regimen}
          </span>
          <span className="bar bar-alert-strong" style={{ width: `${(count / max) * 100}%` }} />
          <strong>{count}</strong>
        </div>
      ))}
    </div>
  );
}

function TrendCard({ to }: { to: string }) {
  const navigate = useNavigate();
  const recent = useApi<SymptomStat[]>(`/api/stats/symptoms?from=${addDays(to, -6)}&to=${to}`);
  const before = useApi<SymptomStat[]>(`/api/stats/symptoms?from=${addDays(to, -13)}&to=${addDays(to, -7)}`);
  const previous = new Map((before.data ?? []).map((row) => [row.symptom, row.reports]));
  const rising = (recent.data ?? [])
    .filter((row) => row.alerts === 0)
    .map((row) => ({ ...row, before: previous.get(row.symptom) ?? 0 }))
    .filter((row) => row.reports > row.before)
    .sort((left, right) => right.reports - right.before - (left.reports - left.before))[0];

  return (
    <OutlinedCard className="card trend-card">
      <div className="row top">
        <SvgIcon svg={trendingUpIcon} className="trend-icon" />
        <div className="column">
          <span className="overline">Možný trend · zatím bez upozornění</span>
          {rising ? (
            <>
              <strong>{rising.symptom} přibývá</strong>
              <span className="muted">
                Za posledních 7 dní {rising.reports} hlášení u {rising.patients} pacientů, týden předtím {rising.before}.
              </span>
            </>
          ) : (
            <span className="muted">{recent.loading ? 'Počítám…' : 'Žádný příznak bez upozornění nepřibývá.'}</span>
          )}
        </div>
      </div>
      {rising && (
        <FilledTonalButton onClick={() => navigate(symptomHref(rising.symptom))}>Prozkoumat: {rising.patients} pacientů</FilledTonalButton>
      )}
    </OutlinedCard>
  );
}
