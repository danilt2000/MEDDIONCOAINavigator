import { FilledButton, TextButton } from '@navigator/ui';
import { useEffect, useState } from 'react';
import { useApp } from '../app-state';
import { disablePush, enablePush, pushState, type PushState } from '../push';
import { ErrorBanner } from '../ui';

function errorDetail(failure: unknown) {
  const message = failure instanceof Error ? failure.message : String(failure);
  try {
    const detail = (JSON.parse(message) as { detail?: unknown }).detail;
    return typeof detail === 'string' ? detail : message;
  } catch {
    return message;
  }
}

function PushCard() {
  const { t, patientId } = useApp();
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    pushState().then(setState, () => setState('unsupported'));
  }, []);
  if (!state) return null;

  const run = async (action: () => Promise<PushState>) => {
    setBusy(true);
    setError(null);
    try {
      setState(await action());
    } catch (failure) {
      setError(`${t.pushError} ${errorDetail(failure)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card">
      <h2 className="card-title muted">{t.pushTitle}</h2>
      {state === 'off' && (
        <>
          <p className="muted">{t.pushOff}</p>
          <FilledButton disabled={busy} onClick={() => run(() => enablePush(patientId))}>
            {busy ? t.pushEnabling : t.pushEnable}
          </FilledButton>
        </>
      )}
      {state === 'on' && (
        <div className="list-row">
          <span className="muted">{t.pushOn}</span>
          <TextButton disabled={busy} onClick={() => run(() => disablePush().then(() => 'off' as const))}>
            {t.pushDisable}
          </TextButton>
        </div>
      )}
      {state === 'ios-install' && <p className="muted">{t.pushIosInstall}</p>}
      {state === 'denied' && <p className="muted">{t.pushDenied}</p>}
      {state === 'unsupported' && <p className="muted">{t.pushUnsupported}</p>}
      {error && <ErrorBanner message={error} />}
    </section>
  );
}

export function Settings() {
  const { t } = useApp();
  return (
    <main className="content">
      <h1 className="title">{t.navSettings}</h1>
      <PushCard />
    </main>
  );
}
