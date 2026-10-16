import type { DoctorSummary, PatientDetail, PatientSymptom, TimelineItem, Trend, TriageOutput } from '@navigator/api';
import { FilledTonalButton, OutlinedCard, SvgIcon, TriageChip } from '@navigator/ui';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { useShell } from '../App';
import { Breadcrumbs, Load, RiskBadges, SummaryView, TaskActions, TriageExplanation, useTrailState } from '../components';
import { assignmentIcon, chatIcon, descriptionIcon, eventBusyIcon, groupsIcon, radiologyIcon, scienceIcon } from '../icons';
import { fmtDay, fmtDayTime, shortRegimen, TASK_STATUS, useApi } from '../lib';
import { GradeBadge } from './Symptom';

const KIND: Record<TimelineItem['kind'], { label: string; icon: string }> = {
  checkin: { label: 'Check-in', icon: assignmentIcon },
  lab: { label: 'Laboratoř', icon: scienceIcon },
  team_event: { label: 'Tým', icon: groupsIcon },
  exam: { label: 'Vyšetření', icon: radiologyIcon },
  chat: { label: 'Chat', icon: chatIcon },
  missed: { label: 'Nevyplněno', icon: eventBusyIcon },
};

const PATIENTS = [{ label: 'Pacienti', to: '/pacienti' }];

export function PatientDetailPage() {
  const { id = '' } = useParams();
  const { queue } = useShell();
  const base = `/api/patients/${encodeURIComponent(id)}`;
  const detail = useApi<PatientDetail>(base, 15000);
  const timeline = useApi<TimelineItem[]>(`${base}/timeline`, 30000);
  const triage = useApi<TriageOutput[]>(`${base}/triage`, 30000);
  const [summaryAt, setSummaryAt] = useState<number | null>(null);
  const summary = useApi<DoctorSummary>(summaryAt ? `${base}/summary?reason=na_vyzadani&t=${summaryAt}` : null);
  const symptoms = useApi<PatientSymptom[]>(`/api/stats/patient/${encodeURIComponent(id)}/symptoms`, 30000);
  const name = detail.data?.name ?? id;
  const linkState = useTrailState(PATIENTS, name);
  const mark = `?pacient=${encodeURIComponent(id)}`;

  return (
    <div className="page">
      <Breadcrumbs fallback={PATIENTS} current={name} />
      <Load source={detail}>
        {(patient) => (
          <OutlinedCard className="card patient-head">
            <div className="row space top">
              <div className="column">
                <h1>
                  {patient.name}, {patient.age} let <span className="muted small">{patient.patient_id}</span>
                </h1>
                <p>
                  {patient.diagnosis} ({patient.icd10}) · {patient.stage}
                </p>
                <p className="muted">
                  {patient.regimen}
                  {patient.cycle != null && ` · cyklus ${patient.cycle}`}
                  {patient.cycle_day != null && `, den ${patient.cycle_day}`} · záměr {patient.intent}
                </p>
                <div className="row wrap">
                  {patient.last_level && <TriageChip level={patient.last_level} withStep />}
                  {patient.risk_badges.includes('nadir') && <span className="risk-badge strong">Nadir D7–14</span>}
                  <RiskBadges badges={patient.risk_badges.filter((badge) => badge !== 'nadir')} />
                </div>
              </div>
              <div className="column end">
                <FilledTonalButton onClick={() => setSummaryAt(Date.now())}>
                  <SvgIcon slot="icon" svg={descriptionIcon} />
                  Vytvořit souhrn
                </FilledTonalButton>
                {patient.open_task && (
                  <span className="status-pill" data-status={patient.open_task.status}>
                    Úkol: {TASK_STATUS[patient.open_task.status] ?? patient.open_task.status}
                  </span>
                )}
              </div>
            </div>
            {patient.open_task && (
              <TaskActions
                task={patient.open_task}
                onDone={() => {
                  detail.reload();
                  queue.reload();
                }}
              />
            )}
            <div className="context-links">
              <span className="overline">Souvislosti</span>
              <Link className="context-link" to={`/monitoring/lecba/${encodeURIComponent(shortRegimen(patient.regimen))}${mark}`} state={linkState}>
                Léčba · {shortRegimen(patient.regimen)}
              </Link>
              {(symptoms.data ?? []).map((row) => (
                <Link
                  key={row.symptom}
                  className="context-link"
                  to={`/monitoring/priznak/${encodeURIComponent(row.symptom)}${mark}`}
                  state={linkState}
                  title={`${row.reports}× nahlášeno, nejvýše stupeň ${row.max_grade}`}
                >
                  <GradeBadge grade={row.max_grade} />
                  {row.symptom}
                </Link>
              ))}
            </div>
            <dl className="facts">
              <dt>ECOG</dt>
              <dd>{patient.ecog}</dd>
              <dt>Komorbidity</dt>
              <dd>{patient.comorbidities.join(', ') || '—'}</dd>
              <dt>Alergie</dt>
              <dd>{patient.allergies.join(', ') || '—'}</dd>
              <dt>Vyplňuje</dt>
              <dd>
                {patient.filled_by} · jazyk {patient.lang}
              </dd>
              <dt>Sledování</dt>
              <dd>
                {fmtDay(patient.monitoring.od)} – {fmtDay(patient.monitoring.do)}
              </dd>
            </dl>
            {patient.advance_directive && (
              <div className="directive">
                <strong>Předem vyslovená přání:</strong> {patient.advance_directive}
                <div className="muted small">Informace pro tým – nikdy důvod nedoporučit pomoc.</div>
              </div>
            )}
            {patient.meds.length > 0 && (
              <details>
                <summary>Léky ({patient.meds.length})</summary>
                <table className="table compact">
                  <tbody>
                    {patient.meds.map((med, index) => (
                      <tr key={index}>
                        <th scope="row">{med.lek}</th>
                        <td>{med.davka}</td>
                        <td>{med.frekvence}</td>
                        <td className="muted">
                          {med.typ}
                          {med.pri_potizich && ' · při potížích'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </OutlinedCard>
        )}
      </Load>

      <div className="board">
        <div className="board-main">
          {summaryAt && (
            <OutlinedCard className="card">
              <h2 className="section-title">Souhrn pro lékaře · 30 s</h2>
              <Load source={summary}>{(data) => <SummaryView summary={data} />}</Load>
            </OutlinedCard>
          )}
          <div className="trend-grid">
            <TrendChart base={base} title="Hmotnost (kg)" metric="weight" />
            <TrendChart base={base} title="Krevní tlak (mmHg)" metric="bp_sys" secondMetric="bp_dia" />
            <TrendChart base={base} title="Teplota (°C)" metric="temperature" reference={38} />
            <TrendChart base={base} title="Stolice nad normál" metric="stools" />
            <TrendChart base={base} title="Bolest (NRS 0–10)" metric="pain" />
          </div>
          <OutlinedCard className="card">
            <h2 className="section-title">Vysvětlení triáže po check-inech</h2>
            <Load source={triage} isEmpty={(items) => items.length === 0} emptyText="Zatím žádný vyhodnocený check-in.">
              {(items) => (
                <div className="triage-list">
                  {items.map((output, index) => (
                    <details key={`${output.checkin_id}-${index}`} open={index === 0} className="triage-item">
                      <summary>
                        <TriageChip level={output.uroven} />
                        <span className="muted">{fmtDayTime(output.as_of)}</span>
                        <span className="ellipsis">{output.klicove_nalezy[0] ?? output.zduvodneni}</span>
                      </summary>
                      <TriageExplanation output={output} />
                    </details>
                  ))}
                </div>
              )}
            </Load>
          </OutlinedCard>
        </div>
        <aside className="board-side">
          <OutlinedCard className="card">
            <h2 className="section-title">Časová osa</h2>
            <Load source={timeline} isEmpty={(items) => items.length === 0} emptyText="Časová osa je prázdná.">
              {(items) => (
                <ol className="timeline">
                  {[...items]
                    .sort((left, right) => right.at.localeCompare(left.at))
                    .map((item, index) => (
                      <li key={`${item.ref}-${index}`} data-kind={item.kind}>
                        <SvgIcon svg={KIND[item.kind]?.icon ?? assignmentIcon} />
                        <div className="column">
                          <span className="row wrap gap-4">
                            <strong>{item.title}</strong>
                            {item.level && <TriageChip level={item.level} />}
                          </span>
                          <span className="muted small">
                            {fmtDayTime(item.at)} · {KIND[item.kind]?.label ?? item.kind}
                          </span>
                          {item.detail && <span className="timeline-detail">{item.detail}</span>}
                          {item.kind === 'checkin' && (item.level ?? 0) >= 2 && (
                            <Link className="small" to={`/monitoring/den/${item.at.slice(0, 10)}${mark}`} state={linkState}>
                              Všechna upozornění {fmtDay(item.at.slice(0, 10))} →
                            </Link>
                          )}
                        </div>
                      </li>
                    ))}
                </ol>
              )}
            </Load>
          </OutlinedCard>
        </aside>
      </div>
    </div>
  );
}

function TrendChart({
  base,
  title,
  metric,
  secondMetric,
  reference,
}: {
  base: string;
  title: string;
  metric: string;
  secondMetric?: string;
  reference?: number;
}) {
  const first = useApi<Trend>(`${base}/trends?metric=${metric}`);
  const second = useApi<Trend>(secondMetric ? `${base}/trends?metric=${secondMetric}` : null);
  const rows = new Map<string, Record<string, number | string>>();
  for (const [key, trend] of [
    [metric, first.data],
    [secondMetric, second.data],
  ] as const) {
    trend?.points.forEach((point) => rows.set(point.at, { ...rows.get(point.at), at: point.at, [key!]: point.value }));
  }
  const data = [...rows.values()].sort((left, right) => String(left.at).localeCompare(String(right.at)));

  return (
    <OutlinedCard className="card trend-card-small">
      <h3 className="section-title small">{title}</h3>
      <Load source={first} isEmpty={() => data.length === 0} emptyText="Bez měření.">
        {() => (
          <ResponsiveContainer width="100%" height={150}>
            <LineChart data={data}>
              <CartesianGrid vertical={false} stroke="var(--md-sys-color-outline-variant)" />
              <XAxis dataKey="at" tickFormatter={fmtDay} tick={{ fontSize: 11 }} minTickGap={16} />
              <YAxis width={40} tick={{ fontSize: 11 }} domain={['auto', 'auto']} tickFormatter={(value: number) => String(Number(value.toFixed(1)))} />
              <Tooltip labelFormatter={(label) => fmtDayTime(String(label))} />
              {reference !== undefined && <ReferenceLine y={reference} stroke="var(--chart-4)" strokeDasharray="4 4" label={{ value: `${reference}`, fontSize: 11 }} />}
              <Line isAnimationActive={false} type="linear" dataKey={metric} name={secondMetric ? 'systolický' : title} stroke="var(--md-sys-color-primary)" dot={{ r: 3 }} connectNulls />
              {secondMetric && <Line isAnimationActive={false} type="linear" dataKey={secondMetric} name="diastolický" stroke="var(--md-sys-color-tertiary)" dot={{ r: 3 }} connectNulls />}
              {secondMetric && <Legend />}
            </LineChart>
          </ResponsiveContainer>
        )}
      </Load>
    </OutlinedCard>
  );
}
