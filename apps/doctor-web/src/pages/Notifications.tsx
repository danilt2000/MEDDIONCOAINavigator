import playIcon from '@material-symbols/svg-400/outlined/play_arrow.svg?raw';
import { api, type NotificationCandidate, type NotificationLogEntry, type NotificationPreview, type NotificationRule } from '@navigator/api';
import { OutlinedButton, OutlinedCard, SvgIcon, Switch } from '@navigator/ui';
import { useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router';
import { Load } from '../components';
import { fmtDayTime, useApi } from '../lib';
import { detailText } from './PushTest';

const RESULT: Record<NotificationLogEntry['result'], string> = { sent: 'odesláno', no_device: 'bez zařízení', failed: 'chyba' };
const SOURCE: Record<NotificationLogEntry['source'], string> = { scheduler: 'plánovač', event: 'událost', manual: 'ručně' };
const TIME_PARAMS: Record<string, string> = { time: 'Čas', start: 'Od', end: 'Do' };
const DAY_OPTIONS = Array.from({ length: 14 }, (_, index) => index + 1);

type RuleChange = Partial<Pick<NotificationRule, 'enabled' | 'params'>>;
type PreviewItem = NotificationPreview['rules'][number];

export function NotificationsPage() {
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Notifikace</h1>
          <p className="muted">
            Push notifikace na telefony pacientů: ruční odeslání, automatická pravidla podle demo hodin a historie toho, co se odeslalo nebo
            přeskočilo.
          </p>
        </div>
      </div>
      <nav className="tabs subtabs" aria-label="Notifikace">
        <NavLink to="/notifikace" end>
          Odeslat
        </NavLink>
        <NavLink to="/notifikace/pravidla">Pravidla</NavLink>
        <NavLink to="/notifikace/historie">Historie</NavLink>
      </nav>
      <Outlet />
    </div>
  );
}

export function NotificationRulesPage() {
  const rules = useApi<NotificationRule[]>('/api/notifications/rules');
  const preview = useApi<NotificationPreview>('/api/notifications/preview', 10000);
  const [error, setError] = useState<string | null>(null);

  const save = async (rule: NotificationRule, change: RuleChange) => {
    setError(null);
    try {
      await api.put('/api/notifications/rules', [{ id: rule.id, enabled: change.enabled ?? rule.enabled, params: change.params ?? rule.params }]);
    } catch (failure) {
      setError(detailText(failure));
    }
    rules.reload();
    preview.reload();
  };

  return (
    <>
      <div className="row space wrap">
        <h2 className="section-title">Nastavení pravidel pro notifikace</h2>
        {preview.data && <span className="muted small">Demo hodiny: {fmtDayTime(preview.data.now)} · náhled se obnovuje každých 10 s</span>}
      </div>
      <p className="muted">
        Text notifikace nikdy neobsahuje zdravotní údaje, je vidět na zamčené obrazovce. Každé pravidlo upozorní pacienta nejvýš jednou denně a push
        dostane jen pacient s přihlášeným zařízením; ostatní se v historii zapíšou jako „bez zařízení“.
      </p>
      {error && (
        <p className="error-text" role="status">
          {error}
        </p>
      )}
      <Load source={rules} isEmpty={(list) => list.length === 0}>
        {(list) => (
          <div className="two-col">
            {list.map((rule) => (
              <RuleCard
                key={rule.id}
                rule={rule}
                preview={preview.data?.rules.find((item) => item.rule_id === rule.id)}
                onSave={(change) => save(rule, change)}
                onRan={preview.reload}
              />
            ))}
          </div>
        )}
      </Load>
    </>
  );
}

function RuleCard({ rule, preview, onSave, onRan }: { rule: NotificationRule; preview?: PreviewItem; onSave: (change: RuleChange) => void; onRan: () => void }) {
  const [running, setRunning] = useState(false);
  const [outcome, setOutcome] = useState<string | null>(null);
  const setParam = (key: string, value: string | number) => value !== rule.params[key] && onSave({ params: { ...rule.params, [key]: value } });

  const run = async () => {
    setRunning(true);
    setOutcome(null);
    try {
      const entries = await api.post<NotificationLogEntry[]>(`/api/notifications/rules/${rule.id}/run`);
      const count = (result: NotificationLogEntry['result']) => entries.filter((entry) => entry.result === result).length;
      setOutcome(entries.length ? `Odesláno ${count('sent')} · bez zařízení ${count('no_device')} · chyba ${count('failed')}` : 'Teď není koho upozornit.');
    } catch (failure) {
      setOutcome(detailText(failure));
    } finally {
      setRunning(false);
      onRan();
    }
  };

  return (
    <OutlinedCard className="card">
      <div className="row space top">
        <div className="column">
          <h3 className="section-title">{rule.name}</h3>
          {preview && (
            <span className="status-pill rule-status" data-due={preview.due}>
              {preview.status}
            </span>
          )}
        </div>
        <Switch
          aria-label={`${rule.name}: zapnuto`}
          selected={rule.enabled}
          onChange={(event) => onSave({ enabled: (event.target as HTMLInputElement & { selected: boolean }).selected })}
        />
      </div>
      <p className="muted">{rule.description}</p>
      {Object.keys(rule.params).length > 0 && (
        <div className="row wrap">
          {Object.entries(rule.params).map(([key, value]) =>
            key === 'days' ? (
              <label key={key} className="row gap-4">
                Počet dní bez check-inu
                <select className="native-input" value={value} onChange={(event) => setParam(key, Number(event.target.value))}>
                  {DAY_OPTIONS.map((days) => (
                    <option key={days} value={days}>
                      {days}
                    </option>
                  ))}
                </select>
                (vysoké riziko o den dřív)
              </label>
            ) : (
              <label key={key} className="row gap-4">
                {TIME_PARAMS[key] ?? key}
                <input className="native-input" type="time" defaultValue={String(value)} onBlur={(event) => event.target.value && setParam(key, event.target.value)} />
              </label>
            ),
          )}
        </div>
      )}
      {rule.title && (
        <div className="lock-screen">
          <span className="label">Na zamčené obrazovce</span>
          <strong>{rule.title}</strong>
          <span>{rule.body}</span>
          <span className="muted small">
            Otevře: <code>{rule.opens}</code>
          </span>
        </div>
      )}
      {rule.kind !== 'quiet' && (
        <>
          <span className="label">{rule.kind === 'event' ? 'Dnešní události' : 'Koho by upozornilo teď'}</span>
          {!preview ? (
            <span className="muted small">Načítám náhled…</span>
          ) : preview.candidates.length === 0 ? (
            <span className="muted small">Nikoho.</span>
          ) : (
            <ul className="tight candidates">
              {preview.candidates.map((candidate) => (
                <li key={candidate.patient_id}>
                  <Link to={`/pacienti/${encodeURIComponent(candidate.patient_id)}`}>{candidate.patient_id}</Link> · {candidate.reason}{' '}
                  <CandidateBadge candidate={candidate} />
                </li>
              ))}
            </ul>
          )}
          <div className="actions">
            <OutlinedButton disabled={running} onClick={run}>
              <SvgIcon slot="icon" svg={playIcon} />
              Spustit teď
            </OutlinedButton>
            {outcome && (
              <span className="muted" role="status">
                {outcome}
              </span>
            )}
          </div>
        </>
      )}
    </OutlinedCard>
  );
}

function CandidateBadge({ candidate }: { candidate: NotificationCandidate }) {
  if (candidate.fired_today === 'sent') return <span className="risk-badge">dnes odesláno</span>;
  if (candidate.fired_today === 'failed') return <span className="risk-badge strong">dnes selhalo</span>;
  if (!candidate.has_device) return <span className="risk-badge muted-badge">bez zařízení</span>;
  return <span className="risk-badge">má zařízení</span>;
}

export function NotificationLogPage() {
  const log = useApi<NotificationLogEntry[]>('/api/notifications/log', 5000);
  return (
    <>
      <p className="muted">Nejnovější nahoře · čas podle demo hodin · historie se drží v paměti serveru do jeho restartu.</p>
      <OutlinedCard className="card flush">
        <Load source={log} isEmpty={(list) => list.length === 0} emptyText="Zatím se nic neodeslalo ani nepřeskočilo.">
          {(list) => (
            <table className="table compact">
              <thead>
                <tr>
                  <th>Čas</th>
                  <th>Pacient</th>
                  <th>Pravidlo</th>
                  <th>Důvod</th>
                  <th>Zařízení · kanál</th>
                  <th>Výsledek</th>
                </tr>
              </thead>
              <tbody>
                {list.map((entry) => (
                  <tr key={entry.id}>
                    <td className="nowrap">{fmtDayTime(entry.at)}</td>
                    <td>
                      <Link to={`/pacienti/${encodeURIComponent(entry.patient_id)}`}>{entry.patient_id}</Link> · {entry.patient_name}
                    </td>
                    <td>
                      {entry.rule_name}
                      <div className="muted small">{SOURCE[entry.source]}</div>
                    </td>
                    <td>{entry.reason}</td>
                    <td>
                      {entry.device ?? '—'}
                      <div className="muted small">{entry.channel}</div>
                    </td>
                    <td>
                      <span className="status-pill" data-result={entry.result}>
                        {RESULT[entry.result]}
                      </span>
                      {entry.detail && <div className="muted small">{entry.detail}</div>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Load>
      </OutlinedCard>
    </>
  );
}
