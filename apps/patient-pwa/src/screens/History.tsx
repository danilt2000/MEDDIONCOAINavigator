import assignmentIcon from '@material-symbols/svg-400/outlined/assignment.svg?raw';
import chatIcon from '@material-symbols/svg-400/outlined/chat.svg?raw';
import eventBusyIcon from '@material-symbols/svg-400/outlined/event_busy.svg?raw';
import supportIcon from '@material-symbols/svg-400/outlined/support_agent.svg?raw';
import type { TimelineItem, TriageOutput } from '@navigator/api';
import { LinearProgress, SvgIcon, TriageChip } from '@navigator/ui';
import { useNavigate } from 'react-router';
import { formatDay, formatTime, useApi, useApp } from '../app-state';
import { ErrorBanner } from '../ui';

const ICONS: Record<string, string> = {
  checkin: assignmentIcon,
  missed: eventBusyIcon,
  team_event: supportIcon,
  chat: chatIcon,
};

export function History() {
  const { t, lang, locale, patientId } = useApp();
  const navigate = useNavigate();
  const timeline = useApi<TimelineItem[]>(`/api/patients/${patientId}/timeline`);
  const triage = useApi<TriageOutput[]>(`/api/patients/${patientId}/triage`);
  const items = (timeline.data ?? []).filter((item) => item.kind in ICONS).sort((a, b) => b.at.localeCompare(a.at));
  const days = new Map<string, TimelineItem[]>();
  for (const item of items) {
    const day = formatDay(new Date(item.at), locale);
    days.set(day, [...(days.get(day) ?? []), item]);
  }

  return (
    <main className="content">
      <h1 className="title">{t.historyTitle}</h1>
      {timeline.loading && !timeline.data && <LinearProgress indeterminate />}
      {timeline.error && <ErrorBanner message={timeline.data ? t.staleData : t.loadError} onRetry={timeline.reload} />}
      {!timeline.loading && !items.length && !timeline.error && <p className="muted">{t.historyEmpty}</p>}
      {[...days].map(([day, dayItems]) => (
        <section key={day} className="timeline-day">
          <h2 className="overline">{day}</h2>
          {dayItems.map((item) => {
            const output = item.kind === 'checkin' ? triage.data?.find((result) => result.checkin_id === item.ref) : undefined;
            const level = item.level ?? output?.uroven;
            const content = (
              <>
                <SvgIcon svg={ICONS[item.kind]} />
                <span className="timeline-body">
                  <span className="strong">{item.kind === 'team_event' ? item.title : item.kind === 'chat' && !item.title.includes('navigátor') ? t.you : t[`kind_${item.kind as 'checkin'}`]}</span>
                  {item.detail && <span className="muted clamp">{item.detail}</span>}
                  {level && <TriageChip level={level} lang={lang} withStep />}
                </span>
                <span className="muted small">{formatTime(new Date(item.at), locale)}</span>
              </>
            );
            return output ? (
              <button key={item.ref + item.at} type="button" className="timeline-item list-button" onClick={() => navigate('/vysledek', { state: { output } })}>
                {content}
              </button>
            ) : (
              <div key={item.ref + item.at} className="timeline-item">
                {content}
              </div>
            );
          })}
        </section>
      ))}
    </main>
  );
}
