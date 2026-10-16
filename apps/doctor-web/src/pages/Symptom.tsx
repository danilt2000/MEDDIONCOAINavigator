import type { SymptomPatient } from '@navigator/api';
import { ChipSet, FilterChip, OutlinedCard } from '@navigator/ui';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { useShell } from '../App';
import { Kpi, Load, RiskBadges } from '../components';
import { addDays, daysBetween, fmtDay, fmtMinutesAgo, shortRegimen, useApi, useNow } from '../lib';

const RISK_FILTERS = ['IO', 'FP', 'irinotekan', 'antikoagulace'];
const GRADE_FILTERS = [
  { min: 0, label: 'Všechny stupně' },
  { min: 2, label: 'Stupeň 2 a víc' },
  { min: 3, label: 'Stupeň 3 a víc' },
];
export const controlled = (update: () => void) => (event: { preventDefault: () => void }) => {
  event.preventDefault();
  update();
};

const GRADE_LABEL = ['bez potíží nebo bez hlášení', 'stupeň 1', 'stupeň 2', 'stupeň 3', 'stupeň 4'];

export function GradeBadge({ grade }: { grade: number }) {
  return (
    <span className="grade-badge" data-grade={Math.min(grade, 4)} title={GRADE_LABEL[Math.min(grade, 4)]}>
      {grade}
    </span>
  );
}

export function SymptomPage() {
  const { symptom = '' } = useParams();
  const { range, queue, offsetMs } = useShell();
  const now = useNow(offsetMs, 30000);
  const rows = useApi<SymptomPatient[]>(`/api/stats/symptom/${encodeURIComponent(symptom)}`);
  const [minGrade, setMinGrade] = useState(0);
  const [risks, setRisks] = useState<string[]>([]);
  const [waitingOnly, setWaitingOnly] = useState(false);

  const openTask = (patientId: string) => queue.data?.find((item) => item.patient_id === patientId && item.status !== 'completed');

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Drobečková navigace">
        <Link to="/monitoring">Monitoring</Link> › <span aria-current="page">{symptom}</span>
      </nav>
      <div className="page-head">
        <div>
          <h1>{symptom}</h1>
          <p className="muted">Stupeň podle odpovědí v dotazníku MEDDI a zprávy pacienta</p>
        </div>
      </div>
      <ChipSet className="filters">
        {GRADE_FILTERS.map((filter) => (
          <FilterChip key={filter.min} label={filter.label} selected={minGrade === filter.min} onClick={controlled(() => setMinGrade(filter.min))} />
        ))}
        {RISK_FILTERS.map((risk) => (
          <FilterChip
            key={risk}
            label={risk}
            selected={risks.includes(risk)}
            onClick={controlled(() =>
              setRisks((current) => (current.includes(risk) ? current.filter((item) => item !== risk) : [...current, risk])),
            )}
          />
        ))}
        <FilterChip label="Jen čekající na reakci" selected={waitingOnly} onClick={controlled(() => setWaitingOnly((value) => !value))} />
      </ChipSet>
      <Load source={rows} isEmpty={(items) => items.length === 0} emptyText="Tento příznak v období nikdo nehlásil.">
        {(items) => {
          const reported = (item: SymptomPatient) => item.series.filter((point) => point.grade > 0);
          const lastReport = (item: SymptomPatient) => reported(item).map((point) => point.date).sort().at(-1) ?? '';
          const visible = items
            .filter((item) => item.max_grade >= minGrade)
            .filter((item) => risks.every((risk) => item.risk_badges.includes(risk)))
            .filter((item) => !waitingOnly || openTask(item.patient_id))
            .sort(
              (left, right) =>
                Number(!!openTask(right.patient_id)) - Number(!!openTask(left.patient_id)) ||
                right.max_grade - left.max_grade ||
                lastReport(right).localeCompare(lastReport(left)),
            );
          const allDates = items.flatMap((item) => item.series.map((point) => point.date.slice(0, 10))).sort();
          const end = allDates.at(-1) ?? range.to;
          const start = [allDates[0] ?? range.from, addDays(end, 1 - range.days)].sort().at(-1)!;
          const days = daysBetween(start, end);
          const byRegimen = new Map<string, number>();
          items
            .filter((item) => item.max_grade >= 2)
            .forEach((item) => byRegimen.set(shortRegimen(item.regimen), (byRegimen.get(shortRegimen(item.regimen)) ?? 0) + 1));
          const regimenRows = [...byRegimen].sort((left, right) => right[1] - left[1]).slice(0, 4);
          const regimenMax = Math.max(1, ...regimenRows.map(([, count]) => count));

          return (
            <>
              <div className="kpi-row">
                <Kpi label="Pacienti" value={items.length} hint={`${items.filter((item) => item.max_grade >= 2).length} se stupněm 2 a víc`} />
                <Kpi label="Hlášení" value={items.reduce((sum, item) => sum + reported(item).length, 0)} hint="stupeň 1 a víc" />
                <Kpi
                  label="Čeká na reakci"
                  value={items.filter((item) => openTask(item.patient_id)).length}
                  tone={items.some((item) => openTask(item.patient_id)) ? 'alert' : 'ok'}
                />
                <div className="kpi">
                  <span className="kpi-label">Stupeň 2+ podle léčby</span>
                  <div className="regimen-bars compact">
                    {regimenRows.map(([regimen, count]) => (
                      <div key={regimen} className="regimen-row">
                        <span className="ellipsis" title={regimen}>
                          {regimen}
                        </span>
                        <span className="bar bar-alert-strong" style={{ width: `${(count / regimenMax) * 100}%` }} />
                        <strong>{count}</strong>
                      </div>
                    ))}
                    {!regimenRows.length && <span className="muted">nikdo</span>}
                  </div>
                </div>
              </div>
              <OutlinedCard className="card">
                <div className="row space">
                  <h2 className="section-title">Pacienti · {visible.length}</h2>
                  <span className="muted small">Nahoře čekající na reakci, pak podle nejvyššího stupně</span>
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Pacient</th>
                      <th>Léčba</th>
                      <th>Max. stupeň</th>
                      <th>
                        Průběh {fmtDay(start)} → {fmtDay(end)}
                      </th>
                      <th>Hlášení</th>
                      <th>Poslední hlášení</th>
                      <th>Stav</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((item) => {
                      const task = openTask(item.patient_id);
                      const grades = new Map(item.series.map((point) => [point.date.slice(0, 10), point.grade]));
                      const last = lastReport(item);
                      return (
                        <tr key={item.patient_id} className={task ? 'row-waiting' : undefined}>
                          <th scope="row">
                            <Link to={`/pacienti/${encodeURIComponent(item.patient_id)}`}>{item.name}</Link>
                            <div className="muted small">{item.patient_id}</div>
                          </th>
                          <td>
                            {shortRegimen(item.regimen)}
                            <RiskBadges badges={item.risk_badges} />
                          </td>
                          <td>
                            <GradeBadge grade={item.max_grade} />
                          </td>
                          <td>
                            <span className="squares" role="img" aria-label={`Průběh: nejvýše stupeň ${item.max_grade}`}>
                              {days.map((day) => {
                                const grade = Math.min(grades.get(day) ?? 0, 4);
                                return <span key={day} className="sq" data-grade={grade} title={`${fmtDay(day)} · ${GRADE_LABEL[grade]}`} />;
                              })}
                            </span>
                          </td>
                          <td>{reported(item).length}</td>
                          <td>{last ? fmtDay(last) : '—'}</td>
                          <td>
                            {task ? (
                              <span className="status-pill" data-status={task.status}>
                                {task.status === 'requested' ? 'Čeká na reakci' : 'Převzato'} · {fmtMinutesAgo(task.created, now)}
                              </span>
                            ) : item.max_grade >= 2 ? (
                              <span className="status-pill" data-status="completed">
                                Vyřešeno
                              </span>
                            ) : (
                              <span className="muted">Bez upozornění</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="legend">
                  {GRADE_LABEL.slice(0, 4).map((label, grade) => (
                    <span key={label} className="row gap-4">
                      <span className="sq" data-grade={grade} aria-hidden="true" />
                      {label}
                    </span>
                  ))}
                </div>
              </OutlinedCard>
            </>
          );
        }}
      </Load>
    </div>
  );
}
