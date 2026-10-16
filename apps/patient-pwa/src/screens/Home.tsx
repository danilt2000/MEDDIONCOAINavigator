import type { TimelineItem, TriageOutput } from '@navigator/api';
import { FilledButton, OutlinedButton, TriageChip } from '@navigator/ui';
import { useNavigate } from 'react-router';
import {
  formatDay,
  formatPhone,
  formatTime,
  nextApplication,
  phoneDigits,
  sameDay,
  shortRegimen,
  store,
  useApi,
  useApp,
} from '../app-state';
import { format } from '../i18n';
import { AiFab, AmbulanceAnd155, ErrorBanner } from '../ui';

function useLastResult() {
  const { patientId } = useApp();
  const triage = useApi<TriageOutput[]>(`/api/patients/${patientId}/triage`);
  const stored = store.get<TriageOutput | null>(`last:${patientId}`, null);
  const fromApi = triage.data?.find((output) => output.zdroj !== 'chat') ?? null;
  const last = !stored || (fromApi && fromApi.as_of >= stored.as_of) ? fromApi : stored;
  return { last, triage };
}

export function Home() {
  const { t, lang, locale, now, patient, patientId, patientError, caregiver, forWhom, contacts } = useApp();
  const navigate = useNavigate();
  const { last, triage } = useLastResult();
  const timeline = useApi<TimelineItem[]>(`/api/patients/${patientId}/timeline`);
  const doneToday = last && sameDay(new Date(last.as_of), now);
  const next = patient ? nextApplication(now, patient.regimen, patient.cycle_day) : null;
  const past = (timeline.data ?? [])
    .filter((item) => item.kind === 'checkin' || item.kind === 'missed')
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, 4);
  const openResult = (output: TriageOutput) => navigate('/vysledek', { state: { output } });
  const triageFor = (ref: string) => triage.data?.find((output) => output.checkin_id === ref);

  return (
    <main className="content home">
      <div className="brand-row">
        <span className="brand">
          <img className="brand-logo" src="/favicon.svg" alt="MEDDI" />
          {t.appName}
        </span>
      </div>

      <div>
        <p className="muted">{formatDay(now, locale)}</p>
        <h1 className="headline">{t.hello}</h1>
        {patient && <p className="muted">{caregiver ? format(t.forWhomHome, forWhom) : patient.name}</p>}
      </div>

      {patientError && !patient && <ErrorBanner message={t.loadError} onRetry={() => location.reload()} />}

      <section className="card">
        <h2 className="card-title-lg">{t.todayTitle}</h2>
        <p className="muted">{doneToday && last ? format(t.todayDone, formatTime(new Date(last.as_of), locale)) : t.todayText}</p>
        {doneToday ? (
          <OutlinedButton onClick={() => navigate('/checkin')}>{t.fillAgain}</OutlinedButton>
        ) : (
          <FilledButton onClick={() => navigate('/checkin')}>{t.fillIn}</FilledButton>
        )}
      </section>

      {patient && (
        <section className="card">
          <h2 className="card-title muted">{t.treatmentTitle}</h2>
          <p className="strong">
            {shortRegimen(patient.regimen)}
            {patient.cycle && patient.cycle_day ? ` · ${format(t.cycleDay, patient.cycle, patient.cycle_day)}` : ''}
          </p>
          {next && <p className="muted">{format(t.nextApplication, formatDay(next, locale))}</p>}
        </section>
      )}

      {past.length > 0 && (
        <section className="card">
          <h2 className="card-title muted">{t.pastTitle}</h2>
          {past.map((item) => {
            const output = triageFor(item.ref);
            const level = item.level ?? output?.uroven;
            const status =
              item.kind === 'missed' ? (
                <span className="muted">{t.missed}</span>
              ) : level === 1 ? (
                <span className="ok-text">{t.noWarning}</span>
              ) : level ? (
                <TriageChip level={level} lang={lang} />
              ) : (
                <span className="muted">{t.noLevel}</span>
              );
            return output ? (
              <button key={item.ref + item.at} type="button" className="list-row list-button" onClick={() => openResult(output)}>
                <span>{formatDay(new Date(item.at), locale)}</span>
                {status}
              </button>
            ) : (
              <div key={item.ref + item.at} className="list-row">
                <span>{formatDay(new Date(item.at), locale)}</span>
                {status}
              </div>
            );
          })}
        </section>
      )}

      <section className="card">
        <h2 className="card-title muted">{t.contactsTitle}</h2>
        <div className="list-row">
          <span>
            {t.monitoringCentre}
            <br />
            <span className="muted small">{contacts?.monitoring_centre.hours || t.monitoringHours}</span>
          </span>
          {contacts?.monitoring_centre.phone && (
            <a className="phone-link" href={`tel:${phoneDigits(contacts.monitoring_centre.phone)}`}>
              {formatPhone(contacts.monitoring_centre.phone)}
            </a>
          )}
        </div>
        <div className="list-row">
          <span>{t.onDuty}</span>
          <a className="phone-link" href={`tel:${phoneDigits(contacts?.on_duty.phone || '724590848')}`}>
            {formatPhone(contacts?.on_duty.phone || '724590848')}
          </a>
        </div>
        <div className="list-row">
          <span>{t.ems}</span>
          <a className="phone-link danger-text" href={`tel:${contacts?.ems.phone || '155'}`}>
            {contacts?.ems.phone || '155'}
          </a>
        </div>
      </section>

      <div className="acute-bar">
        <div className="fab">
          <AiFab />
        </div>
        <p className="strong">{t.acuteTitle}</p>
        <AmbulanceAnd155 />
      </div>
    </main>
  );
}
