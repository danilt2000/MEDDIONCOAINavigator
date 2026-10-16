import type { DoctorSummary, QueueItem, TriageOutput } from '@navigator/api';
import { OutlinedCard, SvgIcon, TriageChip } from '@navigator/ui';
import { Link, useSearchParams } from 'react-router';
import { useShell } from '../App';
import { Load, SummaryView, TaskActions, TriageExplanation } from '../components';
import { bedtimeIcon, timerIcon } from '../icons';
import { fmtDayTime, fmtDuration, shortRegimen, TASK_STATUS, useApi, useNow } from '../lib';

export const byLevelThenSla = (left: QueueItem, right: QueueItem) =>
  right.uroven - left.uroven ||
  (left.sla_do ? new Date(left.sla_do).getTime() : Infinity) - (right.sla_do ? new Date(right.sla_do).getTime() : Infinity);

export function OutOfHoursBadge() {
  return (
    <span className="ooh-badge">
      <SvgIcon svg={bedtimeIcon} />
      mimo pracovní dobu → sloužící lékař
    </span>
  );
}

export function SlaCountdown({ slaDo, level, now }: { slaDo: string | null; level: number; now: number }) {
  if (!slaDo) return <span className="muted">—</span>;
  const remaining = new Date(slaDo).getTime() - now;
  return (
    <span className={remaining < 0 ? 'sla sla-breached' : level === 4 ? 'sla sla-red' : 'sla'}>
      {level === 4 && <SvgIcon svg={timerIcon} />}
      {remaining < 0 ? `po termínu ${fmtDuration(remaining)}` : fmtDuration(remaining)}
    </span>
  );
}

const queueTrail = (taskId: string) => ({ trail: [{ label: 'Fronta', to: `/fronta?task=${encodeURIComponent(taskId)}` }] });

export function QueuePage() {
  const { queue, offsetMs } = useShell();
  const now = useNow(offsetMs);
  const [params, setParams] = useSearchParams();

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Fronta</h1>
          <p className="muted">Seřazeno podle stupně, pak podle SLA · obnovuje se automaticky</p>
        </div>
        {queue.data && (
          <div className="row">
            {([4, 3, 2] as const).map((level) => (
              <span key={level} className="row gap-4">
                <TriageChip level={level} /> <strong>{queue.data!.filter((item) => item.uroven === level).length}</strong>
              </span>
            ))}
          </div>
        )}
      </div>
      <Load source={queue} isEmpty={(items) => items.length === 0} emptyText="Fronta je prázdná – žádný otevřený úkol.">
        {(items) => {
          const sorted = [...items].sort(byLevelThenSla);
          const selected = sorted.find((item) => item.id === params.get('task')) ?? sorted[0];
          return (
            <div className="split">
              <OutlinedCard className="card flush">
                <table className="table queue-table">
                  <thead>
                    <tr>
                      <th>Stupeň</th>
                      <th>Pacient</th>
                      <th>Léčba · den cyklu</th>
                      <th>Proč</th>
                      <th>SLA</th>
                      <th>Stav</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((item) => (
                      <tr
                        key={item.id}
                        className={item.id === selected.id ? 'selected clickable' : 'clickable'}
                        data-level={item.uroven}
                        onClick={() => setParams({ task: item.id })}
                      >
                        <td>
                          <TriageChip level={item.uroven} />
                        </td>
                        <td className="nowrap">
                          <Link
                            to={`/pacienti/${encodeURIComponent(item.patient_id)}`}
                            state={queueTrail(item.id)}
                            onClick={(event) => event.stopPropagation()}
                          >
                            {item.patient_name}, {item.age}
                          </Link>
                          <div className="muted small">{item.patient_id}</div>
                        </td>
                        <td className="regimen-cell">
                          {shortRegimen(item.regimen)}
                          {item.cycle_day != null && <span className="muted"> · D{item.cycle_day}</span>}
                        </td>
                        <td className="why">
                          <div className="ellipsis" title={item.why}>
                            {item.why}
                          </div>
                          {item.out_of_hours && <OutOfHoursBadge />}
                        </td>
                        <td>
                          <SlaCountdown slaDo={item.status === 'requested' ? item.sla_do : null} level={item.uroven} now={now} />
                        </td>
                        <td>
                          <span className="status-pill" data-status={item.status}>
                            {TASK_STATUS[item.status] ?? item.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </OutlinedCard>
              <TaskPanel key={selected.id} task={selected} now={now} onChanged={queue.reload} />
            </div>
          );
        }}
      </Load>
    </div>
  );
}

function TaskPanel({ task, now, onChanged }: { task: QueueItem; now: number; onChanged: () => void }) {
  const summary = useApi<DoctorSummary>(
    `/api/patients/${encodeURIComponent(task.patient_id)}/summary?reason=eskalace&as_of=${encodeURIComponent(task.created)}`,
  );
  const triage = useApi<TriageOutput>(task.checkin_id ? `/api/checkins/${encodeURIComponent(task.checkin_id)}/triage` : null);

  return (
    <aside className="panel-stack" aria-label="Detail úkolu">
      <OutlinedCard className="card">
        <div className="row space">
          <h2 className="title">
            {task.patient_name}, {task.age} let
          </h2>
          <Link to={`/pacienti/${encodeURIComponent(task.patient_id)}`} state={queueTrail(task.id)}>
            Detail pacienta
          </Link>
        </div>
        <p className="muted">
          {shortRegimen(task.regimen)}
          {task.cycle_day != null && ` · den cyklu ${task.cycle_day}`} · vznik {fmtDayTime(task.created)} · {task.owner}
        </p>
        <div className="row wrap">
          <TriageChip level={task.uroven} withStep />
          <SlaCountdown slaDo={task.status === 'requested' ? task.sla_do : null} level={task.uroven} now={now} />
          {task.out_of_hours && <OutOfHoursBadge />}
        </div>
        <p className="why-big">{task.why}</p>
        <TaskActions task={task} onDone={onChanged} />
        {task.notes.length > 0 && (
          <ul className="notes">
            {task.notes.map((note, index) => (
              <li key={index}>
                <span className="muted">
                  {fmtDayTime(note.at)} · {note.author}
                </span>{' '}
                {note.text}
              </li>
            ))}
          </ul>
        )}
      </OutlinedCard>
      <OutlinedCard className="card">
        <h3 className="section-title">Souhrn pro lékaře · 30 s</h3>
        <Load source={summary}>{(data) => <SummaryView summary={data} />}</Load>
      </OutlinedCard>
      {task.checkin_id && (
        <OutlinedCard className="card">
          <h3 className="section-title">Důkazy · proč tento stupeň</h3>
          <Load source={triage}>{(data) => <TriageExplanation output={data} />}</Load>
        </OutlinedCard>
      )}
    </aside>
  );
}
