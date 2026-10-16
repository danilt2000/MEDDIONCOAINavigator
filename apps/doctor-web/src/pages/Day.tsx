import type { QueueItem } from '@navigator/api';
import { OutlinedButton, OutlinedCard, SvgIcon, TriageChip } from '@navigator/ui';
import { Link, useNavigate, useParams } from 'react-router';
import { Kpi, Load } from '../components';
import { chevronLeftIcon, chevronRightIcon } from '../icons';
import { addDays, fmtDay, fmtTime, shortRegimen, TASK_STATUS, useApi } from '../lib';
import { byLevelThenSla, OutOfHoursBadge } from './Queue';

export function DayPage() {
  const { date = '' } = useParams();
  const navigate = useNavigate();
  const rows = useApi<QueueItem[]>(`/api/stats/day/${date}`);

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Drobečková navigace">
        <Link to="/monitoring">Monitoring</Link> › <span aria-current="page">{fmtDay(date)}</span>
      </nav>
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
        {(items) => {
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
                <OutlinedCard key={item.id} className="card day-card">
                  <div className="day-col">
                    <div className="row">
                      <span className="big-time">{item.created ? fmtTime(item.created) : '—'}</span>
                      <TriageChip level={item.uroven} />
                    </div>
                    <Link className="patient-link" to={`/pacienti/${encodeURIComponent(item.patient_id)}`}>
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
        }}
      </Load>
    </div>
  );
}
