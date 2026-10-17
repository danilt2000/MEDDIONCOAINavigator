import type { DemoState, QueueItem } from '@navigator/api';
import { FilledButton, SvgIcon } from '@navigator/ui';
import { useEffect, useMemo, useRef } from 'react';
import { NavLink, Outlet, useNavigate, useOutletContext } from 'react-router';
import { emergencyIcon } from './icons';
import { addDays, beep, fmtDuration, inWorkingHours, isoDay, useApi, useNow, type Loadable } from './lib';

export interface Shell {
  offsetMs: number;
  range: { from: string; to: string; days: number };
  queue: Loadable<QueueItem[]>;
  dataset: string;
}

export const useShell = () => useOutletContext<Shell>();

export function App() {
  const demo = useApi<DemoState>('/api/demo/state', 15000);
  const queue = useApi<QueueItem[]>('/api/queue?status=open', 4000);
  const serverNow = demo.data?.now;
  const offsetMs = useMemo(() => (serverNow ? new Date(serverNow).getTime() - Date.now() : null), [serverNow]);
  // the demo clock runs weeks behind the real one: render nothing time-based (SLA, banner) before it is known
  if (offsetMs === null) return <div className="app" />;

  const to = isoDay(Date.now() + offsetMs);
  const shell: Shell = {
    offsetMs,
    range: { from: addDays(to, -29), to, days: 30 },
    queue,
    dataset: demo.data?.dataset ?? 'dev',
  };
  const openCount = queue.data?.filter((item) => item.status !== 'completed').length ?? 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <img className="brand-logo" src="/favicon.svg" alt="MEDDI" />
          <span>MEDDI navigátor · Monitorovací centrum MOÚ</span>
        </div>
        <Duty offsetMs={offsetMs} />
      </header>
      <nav className="tabs" aria-label="Sekce">
        <NavLink to="/fronta">
          Fronta{openCount > 0 && <span className="count">{openCount}</span>}
        </NavLink>
        <NavLink to="/monitoring">Monitoring</NavLink>
        <NavLink to="/pacienti">Pacienti</NavLink>
        <NavLink to="/pravidla">Pravidla</NavLink>
        <NavLink to="/notifikace">Notifikace</NavLink>
      </nav>
      <RedBanner items={queue.data} offsetMs={offsetMs} />
      <main className="main">
        <Outlet context={shell} />
      </main>
    </div>
  );
}

function Duty({ offsetMs }: { offsetMs: number }) {
  const now = useNow(offsetMs, 15000);
  const working = inWorkingHours(now);
  return (
    <span className="duty">
      <span>Služba: {working ? 'monitorovací centrum (Po–Pá 7:00–15:30)' : 'sloužící lékař MOÚ 724 590 848'}</span>
    </span>
  );
}

function RedBanner({ items, offsetMs }: { items: QueueItem[] | undefined; offsetMs: number }) {
  const navigate = useNavigate();
  const now = useNow(offsetMs);
  const seen = useRef(new Set<string>());
  const red = (items ?? []).filter((item) => item.uroven === 4 && item.status === 'requested');

  useEffect(() => {
    const fresh = red.filter((item) => !seen.current.has(item.id));
    fresh.forEach((item) => seen.current.add(item.id));
    if (fresh.length) beep();
  });

  if (!red.length) return null;
  const first = red[0];
  const remaining = first.sla_do ? new Date(first.sla_do).getTime() - now : null;
  return (
    <div className="red-banner" role="alert">
      <SvgIcon svg={emergencyIcon} />
      <strong>Červená · Volejte ihned</strong>
      <span>
        {first.patient_name}, {first.age} – {first.why}
      </span>
      {remaining !== null && (
        <span className="sla-pill">{remaining >= 0 ? `na převzetí zbývá ${fmtDuration(remaining)}` : `po termínu ${fmtDuration(remaining)}`}</span>
      )}
      {red.length > 1 && <span>+ {red.length - 1} další</span>}
      <FilledButton className="on-red" onClick={() => navigate(`/fronta?task=${encodeURIComponent(first.id)}`)}>
        Otevřít
      </FilledButton>
    </div>
  );
}
