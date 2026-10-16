import { api, type DoctorSummary, type Level, type QueueTask, type TriageOutput } from '@navigator/api';
import {
  CircularProgress,
  Dialog,
  FilledButton,
  OutlinedButton,
  OutlinedTextField,
  SvgIcon,
  TextButton,
  TriageChip,
} from '@navigator/ui';
import { Fragment, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { callIcon, howToRegIcon, refreshIcon, taskAltIcon, videoCallIcon, warningIcon } from './icons';
import { errorText, fmtDayTime, type Loadable } from './lib';

export type Crumb = { label: string; to: string };

const useTrail = (fallback: Crumb[]) => (useLocation().state as { trail?: Crumb[] } | null)?.trail ?? fallback;

export function Breadcrumbs({ fallback, current }: { fallback: Crumb[]; current: string }) {
  const trail = useTrail(fallback);
  return (
    <nav className="breadcrumb" aria-label="Drobečková navigace">
      {trail.map((crumb) => (
        <Fragment key={crumb.to}>
          <Link to={crumb.to}>{crumb.label}</Link> ›{' '}
        </Fragment>
      ))}
      <span aria-current="page">{current}</span>
    </nav>
  );
}

/** Router state for links leaving this page, so the next page's breadcrumb leads back here (filters included). */
export function useTrailState(fallback: Crumb[], current: string) {
  const location = useLocation();
  const trail = useTrail(fallback);
  return { trail: [...trail, { label: current, to: location.pathname + location.search }].slice(-3) };
}

export function Load<T>({
  source,
  isEmpty,
  emptyText = 'Zatím žádná data.',
  children,
}: {
  source: Loadable<T>;
  isEmpty?: (data: T) => boolean;
  emptyText?: string;
  children: (data: T) => ReactNode;
}) {
  if (source.data === undefined) {
    if (source.error) {
      return (
        <div className="state state-error" role="status">
          <SvgIcon svg={warningIcon} />
          <span>{source.error}</span>
          <TextButton onClick={source.reload}>
            <SvgIcon slot="icon" svg={refreshIcon} />
            Zkusit znovu
          </TextButton>
        </div>
      );
    }
    return (
      <div className="state" role="status">
        <CircularProgress indeterminate aria-label="Načítám" />
      </div>
    );
  }
  if (isEmpty?.(source.data)) {
    return (
      <div className="state" role="status">
        {emptyText}
      </div>
    );
  }
  return <>{children(source.data)}</>;
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: 'alert' | 'ok' }) {
  return (
    <div className="kpi" data-tone={tone}>
      <span className="kpi-label">{label}</span>
      <strong className="kpi-value">{value}</strong>
      {hint && <span className="kpi-hint">{hint}</span>}
    </div>
  );
}

export function LevelChip({ level, withStep }: { level: Level | null | undefined; withStep?: boolean }) {
  return level ? <TriageChip level={level} withStep={withStep} /> : <span className="muted">—</span>;
}

export function RiskBadges({ badges }: { badges: string[] | undefined }) {
  if (!badges?.length) return null;
  return (
    <span className="badges">
      {badges.map((badge) => (
        <span key={badge} className="risk-badge">
          {badge}
        </span>
      ))}
    </span>
  );
}

const CONFIDENCE: Record<string, string> = { nizka: 'nízká', stredni: 'střední', vysoka: 'vysoká' };
const SOURCE: Record<string, string> = {
  zprava: 'zpráva',
  dotaznik: 'dotazník',
  priloha: 'příloha',
  chat: 'chat',
  vitalni: 'naměřeno',
  vitalni_funkce: 'naměřeno',
  laborator: 'odběr',
  lab: 'odběr',
  tym: 'tým',
};

export const sourceLabel = (source: string) => SOURCE[source] ?? source;

export function TriageExplanation({ output }: { output: TriageOutput }) {
  return (
    <div className="explain">
      <div className="row wrap">
        <TriageChip level={output.uroven} withStep />
        <span className="muted">
          jistota {CONFIDENCE[output.jistota] ?? output.jistota} · {output.zdroj === 'chat' ? 'chat' : 'check-in'} {output.checkin_id}
        </span>
      </div>
      {output.doporuceny_kontakt && (
        <p className="explain-line">
          <span className="label">Kontakt</span> {output.doporuceny_kontakt}
          {output.sla_do && <> · SLA do {fmtDayTime(output.sla_do)}</>}
        </p>
      )}
      {output.zduvodneni && (
        <p className="explain-line">
          <span className="label">Proč</span> {output.zduvodneni}
        </p>
      )}
      {output.pravidla.length > 0 && (
        <div className="row wrap">
          <span className="label">Pravidla</span>
          {output.pravidla.map((rule) => (
            <code key={rule} className="rule-chip">
              {rule}
            </code>
          ))}
        </div>
      )}
      {output.klicove_nalezy.length > 0 && (
        <div>
          <span className="label">Klíčové nálezy</span>
          <ul className="tight">
            {output.klicove_nalezy.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </div>
      )}
      {output.varovne_priznaky.length > 0 && (
        <div>
          <span className="label">Varovné příznaky</span>
          <ul className="tight">
            {output.varovne_priznaky.map((sign) => (
              <li key={sign}>{sign}</li>
            ))}
          </ul>
        </div>
      )}
      {output.dukazy.length > 0 && (
        <div>
          <span className="label">Citace a zdroje</span>
          <ul className="quotes">
            {output.dukazy.map((evidence, index) => (
              <li key={index}>
                <q>{evidence.citace}</q>
                <span className="muted">
                  {' '}
                  · {sourceLabel(evidence.zdroj)}
                  {evidence.checkin_id && ` · ${evidence.checkin_id}`}
                  {evidence.datum && ` · ${evidence.datum}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {output.doplnujici_otazka && (
        <p className="explain-line">
          <span className="label">Doplňující otázka pacientovi</span> {output.doplnujici_otazka}
        </p>
      )}
    </div>
  );
}

export function SummaryView({ summary }: { summary: DoctorSummary }) {
  const sections: [string, string | null][] = [
    ['Proč teď', summary.proc_ted],
    ['Léčba', summary.lecba],
    ['Vývoj', summary.vyvoj],
    ['Laboratoř', summary.laborator],
    ['Nehlásí', summary.nehlasi],
    ['K posouzení lékařem', summary.k_posouzeni],
  ];
  const structured = sections.some(([, text]) => text);
  return (
    <div className="summary">
      <p className="summary-header">{summary.header}</p>
      {structured ? (
        sections
          .filter(([, text]) => text)
          .map(([label, text]) => (
            <p key={label} className="summary-line">
              <strong>{label}:</strong> {text}
            </p>
          ))
      ) : (
        <p className="summary-line pre">{summary.text}</p>
      )}
      {summary.facts.length > 0 && (
        <details>
          <summary className="muted">Zdroje ({summary.facts.length})</summary>
          <ul className="tight">
            {summary.facts.map((fact, index) => (
              <li key={index}>
                {fact.datum && <span className="muted">{fact.datum} · </span>}
                {fact.text} <span className="muted">({sourceLabel(fact.zdroj)})</span>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="muted small">
        {summary.generated_by === 'llm' ? 'Text napsala AI jen z ověřených faktů výše.' : 'Deterministická šablona z ověřených faktů.'} Bez
        diagnózy a návrhu léčby – rozhoduje lékař.
      </p>
    </div>
  );
}

type TaskAction = 'accept' | 'call' | 'telekonzultace' | 'close';

export function TaskActions({ task, onDone }: { task: QueueTask; onDone: () => void }) {
  const [busy, setBusy] = useState<TaskAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState(false);
  const [note, setNote] = useState('');

  const run = async (action: TaskAction, actionNote?: string) => {
    setBusy(action);
    setError(null);
    try {
      await api.post(`/api/tasks/${encodeURIComponent(task.id)}/action`, { action, note: actionNote || undefined });
      onDone();
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setBusy(null);
    }
  };

  const done = task.status === 'completed';
  return (
    <div className="actions">
      <FilledButton disabled={done || task.status !== 'requested' || busy !== null} onClick={() => run('accept')}>
        <SvgIcon slot="icon" svg={howToRegIcon} />
        Převzít
      </FilledButton>
      <OutlinedButton disabled={done || busy !== null} onClick={() => run('call')}>
        <SvgIcon slot="icon" svg={callIcon} />
        Zavolat
      </OutlinedButton>
      <OutlinedButton disabled={done || busy !== null} onClick={() => run('telekonzultace')}>
        <SvgIcon slot="icon" svg={videoCallIcon} />
        Telekonzultace
      </OutlinedButton>
      <OutlinedButton disabled={done || busy !== null} onClick={() => setClosing(true)}>
        <SvgIcon slot="icon" svg={taskAltIcon} />
        Uzavřít s poznámkou
      </OutlinedButton>
      {error && <span className="error-text">{error}</span>}
      <Dialog open={closing} onClosed={() => setClosing(false)}>
        <div slot="headline">Uzavřít úkol</div>
        <form slot="content" id={`close-${task.id}`} method="dialog" className="dialog-form">
          <OutlinedTextField
            type="textarea"
            label="Poznámka (co bylo domluveno)"
            rows={4}
            value={note}
            onInput={(event) => setNote((event.target as HTMLTextAreaElement).value)}
          />
        </form>
        <div slot="actions">
          <TextButton onClick={() => setClosing(false)}>Zrušit</TextButton>
          <FilledButton
            disabled={!note.trim()}
            onClick={() => {
              setClosing(false);
              run('close', note.trim()).then(() => setNote(''));
            }}
          >
            Uzavřít
          </FilledButton>
        </div>
      </Dialog>
    </div>
  );
}
