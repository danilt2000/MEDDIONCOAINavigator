import type { QueueItem } from '@navigator/api';
import { OutlinedButton, OutlinedCard, SvgIcon, TriageChip } from '@navigator/ui';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { useShell } from '../App';
import { Breadcrumbs, Kpi, Load, useTrailState } from '../components';
import { chevronLeftIcon, chevronRightIcon } from '../icons';
import { addDays, fmtDay, fmtTime, shortRegimen, TASK_STATUS, useApi } from '../lib';
import { byLevelThenSla, OutOfHoursBadge } from './Queue';

const MONITORING = [{ label: 'Monitoring', to: '/monitoring' }];

export function DayPage() {
  const { date = '' } = useParams();
  const navigate = useNavigate();
  const rows = useApi<QueueItem[]>(`/api/stats/day/${date}`);
  const linkState = useTrailState(MONITORING, fmtDay(date));

  return (
    <div className="page">
      <Breadcrumbs fallback={MONITORING} current={fmtDay(date)} />
      <div className="page-head">
        <h1>Upozornění {fmtDay(date)}</h1>
        <div className="row">
          <OutlinedButton onClick={() => navigate(`/monitoring/den/${addDays(date, -1)}`)}>
            <SvgIcon slot="icon" svg={chevronLeftIcon} />
            {fmtDay(addDays(date, -1))}
          </OutlinedButton>
          <OutlinedButton trailingIcon onClick={() => navigate(`/monitoring/den/${addDays(date, 1)}`)}>
            {fmtDay(addDays(date, 1))}
            <SvgIcon slot="icon" svg={chevronRightIcon} />
          </OutlinedButton>
        </div>
      </div>
      <Load source={rows} isEmpty={(items) => items.length === 0} emptyText="Tento den nikdo nedostal stupeň 2 a výš.">
        {(items) => <AlertList items={items} linkState={linkState} />}
      </Load>
    </div>
  );
}

export function RegimenPage() {
  const { regimen = '' } = useParams();
  const { range } = useShell();
  const tasks = useApi<QueueItem[]>('/api/queue?status=all');
  const linkState = useTrailState(MONITORING, regimen);
  const matching = (items: QueueItem[]) =>
    items.filter((item) => shortRegimen(item.regimen) === regimen && item.created.slice(0, 10) >= range.from);

  return (
    <div className="page">
      <Breadcrumbs fallback={MONITORING} current={regimen} />
      <div className="page-head">
        <div>
          <h1>Upozornění · {regimen}</h1>
          <p className="muted">
            {fmtDay(range.from)} – {fmtDay(range.to)}
          </p>
        </div>
      </div>
      <Load source={tasks} isEmpty={(items) => matching(items).length === 0} emptyText="U této léčby nejsou v období žádná upozornění.">
        {(items) => <AlertList items={matching(items)} showDay linkState={linkState} />}
      </Load>
    </div>
  );
}

function AlertList({ items, showDay = false, linkState }: { items: QueueItem[]; showDay?: boolean; linkState: object }) {
  const highlight = useSearchParams()[0].get('pacient');
  const resolved = items.filter((item) => item.status === 'completed').length;
  return (
    <>
      <div className="kpi-row">
        <Kpi label="Upozornění" value={items.length} tone="alert" />
        <Kpi label="Pacienti" value={new Set(items.map((item) => item.patient_id)).size} />
        <Kpi label="Vyřešeno" value={`${resolved} z ${items.length}`} tone={resolved === items.length ? 'ok' : undefined} />
        <Kpi label="Mimo pracovní dobu" value={items.filter((item) => item.out_of_hours).length} />
      </div>
      {[...items].sort(byLevelThenSla).map((item) => (
        <OutlinedCard key={item.id} className={item.patient_id === highlight ? 'card day-card highlight' : 'card day-card'}>
          <div className="day-col">
            <div className="row">
              <span className="big-time">{item.created ? fmtTime(item.created) : '—'}</span>
              {showDay && item.created && <span className="muted">{fmtDay(item.created.slice(0, 10))}</span>}
              <TriageChip level={item.uroven} />
            </div>
            <Link className="patient-link" to={`/pacienti/${encodeURIComponent(item.patient_id)}`} state={linkState}>
              {item.patient_name}, {item.age}
            </Link>
            <span className="muted">
              {item.regimen ? shortRegimen(item.regimen) : ''}
              {item.cycle_day != null && ` · den cyklu ${item.cycle_day}`}
            </span>
          </div>
          <div className="day-col wide">
            <span className="overline">Proč</span>
            <strong>{item.why}</strong>
            {item.out_of_hours && <OutOfHoursBadge />}
          </div>
          <div className="day-col wide">
            <span className="overline">Co následovalo</span>
            {item.notes?.length ? (
              <ol className="steps">
                {item.notes.map((note, index) => (
                  <li key={index}>
                    <span className="step-time">{fmtTime(note.at)}</span>
                    <span>
                      {note.text} <span className="muted">· {note.author}</span>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <span className="muted">Zatím bez záznamu týmu.</span>
            )}
          </div>
          <div className="day-col narrow">
            <span className="status-pill" data-status={item.status}>
              {TASK_STATUS[item.status] ?? item.status}
            </span>
            {item.status !== 'completed' && <Link to={`/fronta?task=${encodeURIComponent(item.id)}`}>Otevřít ve frontě</Link>}
          </div>
        </OutlinedCard>
      ))}
    </>
  );
}
