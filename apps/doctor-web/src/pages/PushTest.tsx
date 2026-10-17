import sendIcon from '@material-symbols/svg-400/outlined/send.svg?raw';
import { ApiError, api, type PatientListItem, type PushDevice, type PushKind, type PushSendResult, type PushTemplate } from '@navigator/api';
import { FilledButton, OutlinedCard, SvgIcon } from '@navigator/ui';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Load } from '../components';
import { errorText, fmtDayTime, useApi } from '../lib';

const patientOrigin = location.origin.replace('://lekar.', '://pacient.').replace(':5174', ':5173');

function detailText(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const { detail } = JSON.parse(error.message);
      if (typeof detail === 'string') return detail;
    } catch {
      /* not a FastAPI error body */
    }
  }
  return errorText(error);
}

export function PushTestPage() {
  const [params, setParams] = useSearchParams();
  const patients = useApi<PatientListItem[]>('/api/patients');
  // one poll feeds both the per-patient counts and the selected patient's device list
  const devices = useApi<PushDevice[]>('/api/push/devices', 5000);
  const counts = new Map<string, number>();
  devices.data?.forEach((device) => counts.set(device.patient_id, (counts.get(device.patient_id) ?? 0) + 1));
  const requested = params.get('patient');
  const items = patients.data ?? [];
  const patientId =
    (items.find((item) => item.patient_id === requested) ?? items.find((item) => counts.has(item.patient_id)) ?? items[0])?.patient_id ?? '';
  const devicesSettled = devices.data !== undefined || devices.error !== null;
  // pin the default in the URL, otherwise a device list reload (e.g. a removed 410 device) switches the patient and drops the send result
  useEffect(() => {
    if (patientId && devicesSettled && patientId !== requested) setParams({ patient: patientId }, { replace: true });
  }, [patientId, devicesSettled, requested, setParams]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Test notifikací</h1>
          <p className="muted">
            Testovací prostředí: odešle skutečnou push notifikaci na telefon pacienta. Po klepnutí se aplikace otevře rovnou na dotazníku.
          </p>
        </div>
      </div>
      <Load source={patients} isEmpty={(items) => items.length === 0} emptyText="Žádní pacienti.">
        {() => {
          const patientDevices = devices.data?.filter((device) => device.patient_id === patientId);
          const appUrl = `${patientOrigin}/?patient=${encodeURIComponent(patientId)}`;
          return (
            <div className="two-col">
              <OutlinedCard className="card">
                <h2 className="section-title">Telefon pacienta</h2>
                <select className="native-select" aria-label="Pacient" value={patientId} onChange={(event) => setParams({ patient: event.target.value })}>
                  {items.map((item) => {
                    const count = counts.get(item.patient_id);
                    return (
                      <option key={item.patient_id} value={item.patient_id}>
                        {`${item.patient_id} · ${item.name}${count ? ` · ${count} zařízení` : ''}`}
                      </option>
                    );
                  })}
                </select>
                <div className="column">
                  <span className="label">Odkaz na aplikaci pacienta</span>
                  <a className="push-link" href={appUrl} target="_blank" rel="noreferrer">
                    {appUrl}
                  </a>
                </div>
                <ol className="tight">
                  <li>Otevřete odkaz výše na telefonu.</li>
                  <li>
                    <strong>iPhone:</strong> Sdílet → Přidat na plochu a aplikaci pak otevřete z plochy (push na iPhonu funguje jen tam, iOS 16.4+).{' '}
                    <strong>Android:</strong> stačí Chrome.
                  </li>
                  <li>
                    V horní liště aplikace musí být vybraný pacient <strong>{patientId}</strong> (aplikace z plochy na iPhonu začíná u výchozího pacienta).
                  </li>
                  <li>Na úvodní obrazovce klepněte na „Zapnout upozornění“ a upozornění povolte.</li>
                  <li>Zařízení se objeví níže.</li>
                </ol>
                <Load
                  source={{ ...devices, data: patientDevices }}
                  isEmpty={(list) => list.length === 0}
                  emptyText="Zatím žádné zařízení. Otevřete odkaz výše na telefonu a zapněte upozornění."
                >
                  {(list) => (
                    <table className="table compact">
                      <thead>
                        <tr>
                          <th>Zařízení</th>
                          <th>Služba</th>
                          <th>Přihlášeno</th>
                          <th>Naposledy odesláno</th>
                          <th>Stav</th>
                        </tr>
                      </thead>
                      <tbody>
                        {list.map((device) => (
                          <tr key={device.id}>
                            <th scope="row">{device.label}</th>
                            <td>{device.service}</td>
                            <td>{fmtDayTime(device.subscribed_at)}</td>
                            <td>{device.last_sent_at ? fmtDayTime(device.last_sent_at) : '—'}</td>
                            <td>{device.last_status ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Load>
              </OutlinedCard>
              <SendCard key={patientId} patientId={patientId} devices={patientDevices} onSent={devices.reload} />
            </div>
          );
        }}
      </Load>
    </div>
  );
}

function SendCard({ patientId, devices, onSent }: { patientId: string; devices: PushDevice[] | undefined; onSent: () => void }) {
  const templates = useApi<PushTemplate[]>(`/api/push/templates?patient_id=${encodeURIComponent(patientId)}`);
  const [kind, setKind] = useState<PushKind>('checkin');
  const [sending, setSending] = useState(false);
  const [outcome, setOutcome] = useState<{ result?: PushSendResult; labels?: Map<string, string>; error?: string } | null>(null);

  const send = async () => {
    // snapshot labels: the backend deletes gone (404/410) devices, so the reloaded list no longer knows them
    const labels = new Map(devices?.map((device) => [device.id, device.label]));
    setSending(true);
    setOutcome(null);
    try {
      setOutcome({ result: await api.post<PushSendResult>('/api/push/send', { patient_id: patientId, kind }), labels });
    } catch (failure) {
      setOutcome({ error: detailText(failure) });
    } finally {
      setSending(false);
      onSent();
    }
  };

  const result = outcome?.result;
  const failures = result?.results.filter((item) => !item.ok) ?? [];

  return (
    <OutlinedCard className="card">
      <h2 className="section-title">Notifikace</h2>
      <Load source={templates} isEmpty={(list) => list.length === 0}>
        {(list) => (
          <div className="push-options" role="radiogroup" aria-label="Šablona notifikace">
            {list.map((template) => (
              <label key={template.kind} className="push-option">
                <input type="radio" name="push-kind" checked={kind === template.kind} onChange={() => setKind(template.kind)} />
                <span className="column">
                  <strong>{template.title}</strong>
                  <span>{template.body}</span>
                  <span className="muted small">
                    Otevře: <code>{template.url.split('?')[0]}</code>
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
      </Load>
      <div className="actions">
        <FilledButton disabled={sending || !devices?.length} onClick={send}>
          <SvgIcon slot="icon" svg={sendIcon} />
          Odeslat na telefon
        </FilledButton>
        {outcome?.error && (
          <span className="error-text" role="status">
            {outcome.error}
          </span>
        )}
      </div>
      {result && (
        <div className="column" role="status">
          <p>Odesláno na {result.sent} zařízení.</p>
          {failures.length > 0 && (
            <ul className="tight error-text">
              {failures.map((item) => (
                <li key={item.device_id}>
                  {outcome?.labels?.get(item.device_id) ?? item.device_id}: {[item.status && `HTTP ${item.status}`, item.error].filter(Boolean).join(' · ') || 'chyba'}
                </li>
              ))}
            </ul>
          )}
          {result.removed > 0 && <p className="muted">Odstraněno {result.removed} neplatných odběrů.</p>}
        </div>
      )}
    </OutlinedCard>
  );
}
