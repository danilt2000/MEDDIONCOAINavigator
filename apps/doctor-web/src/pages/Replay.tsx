import { api, subscribeSse, type DoctorSummary, type EvalReport, type PatientListItem, type ReplayEvent } from '@navigator/api';
import {
  ChipSet,
  FilledButton,
  FilterChip,
  LinearProgress,
  OutlinedButton,
  OutlinedCard,
  OutlinedSelect,
  SelectOption,
  SvgIcon,
  TextButton,
  TriageChip,
} from '@navigator/ui';
import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { LevelChip, Load, SummaryView, TriageExplanation } from '../components';
import { arrowDownIcon, arrowUpIcon, bedtimeIcon, checkIcon, pauseIcon, playIcon, restartIcon, skipNextIcon } from '../icons';
import { errorText, fmtDay, fmtTime, inWorkingHours, pragueClock, useApi, WORK_END, WORK_START } from '../lib';
import { DATASETS } from './Patients';
import { controlled } from './Symptom';

const SPEEDS = [1, 2, 5, 10, 50];
const LEVELS = [1, 2, 3, 4] as const;

interface MetricRow {
  keys: string[];
  label: string;
  target: string;
  ok?: (value: number) => boolean;
  count?: boolean;
}

const METRICS: MetricRow[] = [
  { keys: ['checkins'], label: 'Vyhodnocené check-iny', target: '', count: true },
  { keys: ['red_recall'], label: 'Záchyt červených (GT 4 → 4)', target: '100 %', ok: (value) => value >= 100 },
  { keys: ['orange_recall'], label: 'Záchyt oranžových (GT 3 → ≥ 3)', target: '≥ 95 %', ok: (value) => value >= 95 },
  { keys: ['under_triage_by_2'], label: 'Podhodnocení o 2 a více stupňů', target: '0', ok: (value) => value === 0, count: true },
  { keys: ['under_triage'], label: 'Podhodnocení celkem', target: '≤ 3 %', ok: (value) => value <= 3 },
  { keys: ['false_alarms'], label: 'Falešné poplachy (GT 1 → ≥ 2)', target: '≤ 15 %', ok: (value) => value <= 15 },
  { keys: ['false_alarms_3plus'], label: 'Falešné poplachy (GT 1 → ≥ 3)', target: 'informativní' },
  { keys: ['notify_agreement'], label: 'Shoda upozornit tým', target: '≥ 95 %', ok: (value) => value >= 95 },
  { keys: ['routing'], label: 'Směrování (kategorie kontaktu)', target: '≥ 95 %', ok: (value) => value >= 95 },
  { keys: ['routing_exact'], label: 'Kontakt – přesná shoda textu', target: 'informativní' },
  { keys: ['exact_level'], label: 'Přesná shoda stupně', target: '≥ 85 %', ok: (value) => value >= 85 },
  { keys: ['step_agreement'], label: 'Shoda doporučeného kroku', target: 'informativní' },
  { keys: ['validator_pass'], label: 'Texty prošly validátorem', target: '100 %', ok: (value) => value >= 100 },
];

function fmtMetric(value: unknown, count?: boolean): string {
  if (typeof value !== 'number') return value == null ? '—' : String(value);
  return count ? String(value) : `${value.toFixed(1).replace('.', ',')} %`;
}

function liveReport(events: ReplayEvent[]): EvalReport {
  const scored = events.filter((event) => event.expected);
  const confusion = LEVELS.map(() => LEVELS.map(() => 0));
  scored.forEach((event) => confusion[event.expected!.uroven - 1][event.output.uroven - 1]++);
  const pct = (hits: number, total: number) => (total ? Math.round((1000 * hits) / total) / 10 : null);
  const where = (test: (event: ReplayEvent) => boolean) => scored.filter(test).length;
  const gt = (level: number) => where((event) => event.expected!.uroven === level);
  const both = (test: (output: ReplayEvent['output'], truth: NonNullable<ReplayEvent['expected']>) => boolean) =>
    where((event) => test(event.output, event.expected!));
  return {
    confusion,
    errors: [],
    metrics: {
      checkins: scored.length,
      red_recall: pct(both((output, truth) => truth.uroven === 4 && output.uroven === 4), gt(4)),
      orange_recall: pct(both((output, truth) => truth.uroven === 3 && output.uroven >= 3), gt(3)),
      under_triage_by_2: both((output, truth) => truth.uroven - output.uroven >= 2),
      under_triage: pct(both((output, truth) => output.uroven < truth.uroven), scored.length),
      false_alarms: pct(both((output, truth) => truth.uroven === 1 && output.uroven >= 2), gt(1)),
      notify_agreement: pct(both((output, truth) => output.upozornit_tym === truth.upozornit_tym), scored.length),
      routing_exact: pct(both((output, truth) => output.doporuceny_kontakt === truth.doporuceny_kontakt), scored.length),
      exact_level: pct(both((output, truth) => output.uroven === truth.uroven), scored.length),
    },
  };
}

export function ReplayPage() {
  const [dataset, setDataset] = useState('dev');
  const [patientId, setPatientId] = useState('');
  const [speed, setSpeed] = useState(5);
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<ReplayEvent[]>([]);
  const [shown, setShown] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [ended, setEnded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runReport, setRunReport] = useState<{ label: string; data: EvalReport } | null>(null);
  const [loadedReport, setLoadedReport] = useState<{ label: string; data: EvalReport } | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const received = useRef(0);
  const jumpToEnd = useRef(false);
  const patients = useApi<PatientListItem[]>(`/api/patients?dataset=${dataset}`);

  useEffect(() => {
    if (!runId) return;
    const seen = new Set<string>();
    const unsubscribe = subscribeSse(`/api/replay/${encodeURIComponent(runId)}/events`, ({ event, data }) => {
      if (event === 'end') {
        setEnded(true);
        unsubscribe();
        api.get<EvalReport>(`/api/eval/${encodeURIComponent(runId)}`).then(
          (result) => setRunReport({ label: 'Tento běh', data: result }),
          () => undefined,
        );
        return;
      }
      if (event === 'error-event') {
        setError(`Replay skončil chybou: ${(data as { message?: string })?.message ?? data}`);
        return;
      }
      const item = data as ReplayEvent;
      if (!item?.checkin_id || seen.has(item.checkin_id)) return;
      seen.add(item.checkin_id);
      received.current = seen.size;
      setEvents((current) => [...current, item]);
      if (jumpToEnd.current) setShown(seen.size);
    });
    return unsubscribe;
  }, [runId]);

  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => setShown((count) => Math.min(count + 1, received.current)), 1000 / speed);
    return () => clearInterval(id);
  }, [playing, speed]);

  useEffect(() => {
    if (ended && shown >= events.length) setPlaying(false);
  }, [ended, shown, events.length]);

  const reset = () => {
    setRunId(null);
    setPlaying(false);
    setEvents([]);
    setShown(0);
    setEnded(false);
    received.current = 0;
    jumpToEnd.current = false;
  };

  const start = async (autoplay: boolean) => {
    setError(null);
    setEvents([]);
    setShown(autoplay ? 0 : 1);
    setEnded(false);
    setRunReport(null);
    setLoadedReport(null);
    setSelectedId(null);
    received.current = 0;
    jumpToEnd.current = false;
    try {
      const result = await api.post<{ run_id: string }>('/api/replay', {
        dataset,
        patients: patientId ? [patientId] : undefined,
        speed,
      });
      setRunId(result.run_id);
      setPlaying(autoplay);
    } catch (failure) {
      setRunId(null);
      setError(errorText(failure));
    }
  };

  const loadLatest = async (which: string, label: string) => {
    setError(null);
    try {
      setLoadedReport({ label, data: await api.get<EvalReport>(`/api/eval/latest-${which}`) });
    } catch (failure) {
      setError(errorText(failure));
    }
  };

  const canResume = !!runId && (!ended || shown < events.length);
  const visible = events.slice(0, shown);
  const current = visible.find((event) => event.checkin_id === selectedId) ?? visible.at(-1);
  const live = liveReport(visible);
  const report = loadedReport ?? (runReport && shown >= events.length ? runReport : null);
  const shownReport = report?.data ?? live;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Replay a evaluace</h1>
          <p className="muted">Check-iny chronologicky; v každém okamžiku systém vidí jen to, co bylo známo do té doby.</p>
        </div>
        <div className="row">
          <TextButton onClick={() => loadLatest('dev', 'Poslední běh · vývojová sada')}>Hodnocení dev</TextButton>
          <TextButton onClick={() => loadLatest('rozsirena', 'Poslední běh · rozšířená sada')}>Hodnocení rozšířená</TextButton>
          {loadedReport && <TextButton onClick={() => setLoadedReport(null)}>Živé metriky</TextButton>}
        </div>
      </div>

      <OutlinedCard className="card">
        <div className="row wrap controls">
          <ChipSet>
            {DATASETS.map((item) => (
              <FilterChip
                key={item.id}
                label={item.label}
                selected={dataset === item.id}
                onClick={controlled(() => {
                  setDataset(item.id);
                  setPatientId('');
                  reset();
                })}
              />
            ))}
          </ChipSet>
          <OutlinedSelect
            label="Pacient"
            value={patientId}
            onChange={(event) => {
              setPatientId((event.target as HTMLSelectElement).value);
              reset();
            }}
            className="patient-select"
          >
            <SelectOption value="" selected={patientId === ''}>
              <div slot="headline">Všichni pacienti ({patients.data?.length ?? '…'})</div>
            </SelectOption>
            {(patients.data ?? []).map((patient) => (
              <SelectOption key={patient.patient_id} value={patient.patient_id} selected={patientId === patient.patient_id}>
                <div slot="headline">
                  {patient.patient_id} · {patient.name}
                </div>
              </SelectOption>
            ))}
          </OutlinedSelect>
          <OutlinedSelect label="Rychlost" value={String(speed)} onChange={(event) => setSpeed(Number((event.target as HTMLSelectElement).value))}>
            {SPEEDS.map((value) => (
              <SelectOption key={value} value={String(value)} selected={speed === value}>
                <div slot="headline">{value} check-in/s</div>
              </SelectOption>
            ))}
          </OutlinedSelect>
          <FilledButton onClick={() => (canResume ? setPlaying(true) : start(true))} disabled={playing}>
            <SvgIcon slot="icon" svg={playIcon} />
            {canResume ? 'Pokračovat' : 'Spustit'}
          </FilledButton>
          <OutlinedButton onClick={() => setPlaying(false)} disabled={!playing}>
            <SvgIcon slot="icon" svg={pauseIcon} />
            Pauza
          </OutlinedButton>
          <OutlinedButton
            onClick={() => {
              setPlaying(false);
              if (runId) setShown((count) => Math.min(count + 1, received.current));
              else start(false);
            }}
            disabled={!!runId && ended && shown >= events.length}
          >
            <SvgIcon slot="icon" svg={skipNextIcon} />
            Krok
          </OutlinedButton>
          <OutlinedButton
            onClick={() => {
              jumpToEnd.current = true;
              setShown(received.current);
            }}
            disabled={!runId}
          >
            Na konec
          </OutlinedButton>
          <TextButton onClick={() => start(false)} disabled={!runId}>
            <SvgIcon slot="icon" svg={restartIcon} />
            Znovu
          </TextButton>
          <span className="muted">
            {shown} / {events.length}
            {runId && !ended && ' · načítám…'}
          </span>
        </div>
        {runId && <LinearProgress value={events.length ? shown / events.length : 0} />}
        {error && <p className="error-text">{error}</p>}
      </OutlinedCard>

      <div className="replay-top">
        <ClockCard at={current?.at ?? null} />
        <OutlinedCard className="card">
          <h2 className="section-title">Matice záměn · {report ? report.label : 'živě z přehraných check-inů'}</h2>
          <Confusion matrix={shownReport.confusion} />
        </OutlinedCard>
        <OutlinedCard className="card">
          <h2 className="section-title">Metriky (§13) · {report ? report.label : 'živě'}</h2>
          <Metrics metrics={shownReport.metrics} />
        </OutlinedCard>
      </div>

      <div className="board">
        <OutlinedCard className="card flush board-main">
          <table className="table">
            <thead>
              <tr>
                <th>Čas</th>
                <th>Pacient · check-in</th>
                <th>Predikce</th>
                <th>Ground truth</th>
                <th>Výsledek</th>
                <th>Pravidla</th>
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted center">
                    {runId ? 'Čekám na první check-in…' : 'Vyberte sadu a spusťte replay.'}
                  </td>
                </tr>
              )}
              {[...visible]
                .reverse()
                .slice(0, 300)
                .map((event) => (
                  <tr
                    key={event.checkin_id}
                    className={event.checkin_id === current?.checkin_id ? 'selected clickable' : 'clickable'}
                    onClick={() => setSelectedId(event.checkin_id)}
                  >
                    <td className="nowrap">
                      {fmtDay(event.at)} {fmtTime(event.at)}
                      {!inWorkingHours(event.at) && <SvgIcon svg={bedtimeIcon} className="inline-icon" aria-label="mimo pracovní dobu" />}
                    </td>
                    <td>
                      <button type="button" className="link-button" onClick={() => setSelectedId(event.checkin_id)}>
                        {event.checkin_id}
                      </button>
                    </td>
                    <td>
                      <TriageChip level={event.output.uroven} />
                    </td>
                    <td>
                      <LevelChip level={event.expected?.uroven} />
                    </td>
                    <td>
                      <Outcome predicted={event.output.uroven} expected={event.expected?.uroven} />
                    </td>
                    <td className="rules-cell">
                      {event.output.pravidla.map((rule) => (
                        <code key={rule} className="rule-chip">
                          {rule}
                        </code>
                      ))}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </OutlinedCard>
        <aside className="board-side">
          {current ? (
            <OutlinedCard className="card">
              <h2 className="section-title">{current.checkin_id}</h2>
              <TriageExplanation output={current.output} />
              <p className="explain-line">
                <span className="label">Odpověď pacientovi</span> {current.output.doporuceni_pro_pacienta}
              </p>
              {current.output.uroven >= 3 && <EscalationSummary patientId={current.patient_id} at={current.at} />}
              {current.expected && (
                <div className="expected">
                  <div className="row wrap">
                    <span className="label">Ground truth</span>
                    <TriageChip level={current.expected.uroven} withStep />
                  </div>
                  <p className="small">{current.expected.zduvodneni}</p>
                  <p className="small muted">Kontakt: {current.expected.doporuceny_kontakt ?? '—'}</p>
                </div>
              )}
            </OutlinedCard>
          ) : (
            <OutlinedCard className="card">
              <p className="muted">Detail vybraného check-inu se zobrazí tady.</p>
            </OutlinedCard>
          )}
        </aside>
      </div>

      {report && report.data.errors.length > 0 && <ErrorList errors={report.data.errors} label={report.label} />}
    </div>
  );
}

function EscalationSummary({ patientId, at }: { patientId: string; at: string }) {
  const summary = useApi<DoctorSummary>(
    `/api/patients/${encodeURIComponent(patientId)}/summary?reason=eskalace&as_of=${encodeURIComponent(at)}`,
  );
  return (
    <div className="expected">
      <span className="label">Souhrn pro lékaře při eskalaci</span>
      <Load source={summary}>{(data) => <SummaryView summary={data} />}</Load>
    </div>
  );
}

function Outcome({ predicted, expected }: { predicted: number; expected: number | undefined }) {
  if (!expected) return <span className="muted">—</span>;
  const diff = predicted - expected;
  if (diff === 0)
    return (
      <span className="outcome ok">
        <SvgIcon svg={checkIcon} />
        shoda
      </span>
    );
  return diff < 0 ? (
    <span className="outcome under">
      <SvgIcon svg={arrowDownIcon} />
      podhodnoceno o {-diff}
    </span>
  ) : (
    <span className="outcome over">
      <SvgIcon svg={arrowUpIcon} />
      nadhodnoceno o {diff}
    </span>
  );
}

function ClockCard({ at }: { at: string | null }) {
  const clock = at ? pragueClock(at) : null;
  const weekday = clock ? clock.weekday >= 1 && clock.weekday <= 5 : true;
  const working = at ? inWorkingHours(at) : false;
  return (
    <OutlinedCard className="card clock-card">
      <h2 className="section-title">Simulovaný čas</h2>
      <div className="clock-time">{at ? fmtTime(at) : '--:--'}</div>
      <div className="muted">{at ? fmtDay(at) : 'replay neběží'}</div>
      <div className="hours-track" aria-hidden="true">
        {weekday && <span className="hours-band" style={{ left: `${(WORK_START / 1440) * 100}%`, width: `${((WORK_END - WORK_START) / 1440) * 100}%` }} />}
        {clock && <span className="hours-marker" style={{ left: `${(clock.minutes / 1440) * 100}%` }} />}
      </div>
      <div className="hours-ticks muted small">
        <span>0</span>
        <span>6</span>
        <span>12</span>
        <span>18</span>
        <span>24</span>
      </div>
      {at && (
        <span className={working ? 'hours-state in' : 'hours-state out'}>
          {working ? 'V pracovní době MC (Po–Pá 7:00–15:30)' : 'Mimo pracovní dobu → sloužící lékař / 155'}
        </span>
      )}
    </OutlinedCard>
  );
}

function Confusion({ matrix }: { matrix: number[][] }) {
  const max = Math.max(1, ...matrix.flat());
  return (
    <table className="confusion">
      <thead>
        <tr>
          <th className="corner">GT ↓ / predikce →</th>
          {LEVELS.map((level) => (
            <th key={level}>
              <TriageChip level={level} />
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {LEVELS.map((expected, row) => (
          <tr key={expected}>
            <th>
              <TriageChip level={expected} />
            </th>
            {LEVELS.map((predicted, column) => {
              const value = matrix[row]?.[column] ?? 0;
              const kind = predicted === expected ? 'ok' : predicted < expected ? 'under' : 'over';
              return (
                <td
                  key={predicted}
                  className={`cell-${kind}`}
                  style={{ '--strength': value ? 0.15 + (value / max) * 0.6 : 0 } as CSSProperties}
                  title={`GT ${expected}, predikce ${predicted}: ${value}`}
                >
                  {value}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Metrics({ metrics }: { metrics: EvalReport['metrics'] }) {
  const known = new Set(METRICS.flatMap((row) => row.keys));
  const extra = Object.entries(metrics).filter(([key]) => !known.has(key));
  return (
    <table className="table compact metrics">
      <tbody>
        {METRICS.map((row) => {
          const key = row.keys.find((candidate) => candidate in metrics);
          if (!key) return null;
          const value = metrics[key];
          const pass = typeof value === 'number' && row.ok ? row.ok(value) : null;
          return (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td className="num">{fmtMetric(value, row.count)}</td>
              <td className="muted small">{row.target && `cíl ${row.target}`}</td>
              <td>{pass === null ? null : pass ? <span className="outcome ok">splněno</span> : <span className="outcome under">nesplněno</span>}</td>
            </tr>
          );
        })}
        {extra.map(([key, value]) => (
          <tr key={key}>
            <th scope="row">{key}</th>
            <td className="num">{typeof value === 'number' && !Number.isInteger(value) ? value.toFixed(3) : String(value ?? '—')}</td>
            <td colSpan={2} />
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const ERROR_COLUMNS: Record<string, string> = {
  checkin_id: 'Check-in',
  kind: 'Typ',
  expected: 'GT',
  predicted: 'Predikce',
  rules: 'Pravidla',
  expected_contact: 'Kontakt GT',
  predicted_contact: 'Kontakt predikce',
};

const ERROR_KINDS: Record<string, string> = { under: 'podhodnoceno', over: 'nadhodnoceno', routing: 'jen kontakt' };

function ErrorList({ errors, label }: { errors: Record<string, unknown>[]; label: string }) {
  const preferred = Object.keys(ERROR_COLUMNS).filter((column) => column in (errors[0] ?? {}));
  const columns = preferred.length ? preferred : Object.keys(errors[0] ?? {}).slice(0, 7);
  const show = (value: unknown) => (Array.isArray(value) ? value.join(', ') : typeof value === 'object' && value ? JSON.stringify(value) : String(value ?? '—'));
  return (
    <OutlinedCard className="card flush">
      <h2 className="section-title padded">
        Chyby · {label} · {errors.length}
      </h2>
      <table className="table compact">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{ERROR_COLUMNS[column] ?? column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {errors.slice(0, 100).map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{column === 'kind' ? (ERROR_KINDS[String(row.kind)] ?? show(row.kind)) : show(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </OutlinedCard>
  );
}
