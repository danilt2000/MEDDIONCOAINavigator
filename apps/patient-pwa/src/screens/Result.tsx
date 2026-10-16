import callIcon from '@material-symbols/svg-400/outlined/call.svg?raw';
import checkCircleIcon from '@material-symbols/svg-400/outlined/check_circle.svg?raw';
import emergencyIcon from '@material-symbols/svg-400/outlined/emergency.svg?raw';
import wifiOffIcon from '@material-symbols/svg-400/outlined/wifi_off.svg?raw';
import type { CheckinInput, TriageOutput } from '@navigator/api';
import { FilledTonalButton, OutlinedButton, SvgIcon, TextButton, TRIAGE_LEVELS, TriageChip } from '@navigator/ui';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { callTargets, capitalize, formatDayTime, phoneDigits, shortRegimen, store, useApp } from '../app-state';
import { VITALS, type VitalKey } from '../flow';
import { format } from '../i18n';
import { CallButton, CallButtons, CallNowCard } from '../ui';

interface ResultState {
  output?: TriageOutput;
  checkin?: CheckinInput;
  queued?: boolean;
}

export function Result() {
  const { patientId } = useApp();
  const state = (useLocation().state ?? {}) as ResultState;
  if (state.queued) return <QueuedResult />;
  const output = (state.output?.patient_id === patientId ? state.output : null) ?? store.get<TriageOutput | null>(`last:${patientId}`, null);
  if (!output) return <Navigate to="/" replace />;
  if (output.uroven === 4) return <RedResult output={output} checkin={state.checkin} />;
  if (output.uroven === 1) return <GreenResult output={output} />;
  return <WarningResult output={output} />;
}

function Followup({ output }: { output: TriageOutput }) {
  const { t } = useApp();
  const navigate = useNavigate();
  if (!output.doplnujici_otazka) return null;
  return (
    <section className="card card-tonal">
      <h2 className="card-title">{t.followupTitle}</h2>
      <p className="strong">{output.doplnujici_otazka}</p>
      <FilledTonalButton onClick={() => navigate('/navigator', { state: { followup: output.doplnujici_otazka, patientId: output.patient_id } })}>
        {t.answer}
      </FilledTonalButton>
    </section>
  );
}

function DoneButton() {
  const { t } = useApp();
  const navigate = useNavigate();
  return <OutlinedButton onClick={() => navigate('/')}>{t.done}</OutlinedButton>;
}

function GreenResult({ output }: { output: TriageOutput }) {
  const { t, lang } = useApp();
  const navigate = useNavigate();
  return (
    <main className="content result">
      <span className="result-icon">
        <SvgIcon svg={checkCircleIcon} />
      </span>
      <h1 className="headline">{t.thanks}</h1>
      <p className="muted">{t.greenText}</p>
      <TriageChip level={1} lang={lang} withStep />
      <section className="card">
        <h2 className="card-title">{t.advice}</h2>
        <p>{output.doporuceni_pro_pacienta}</p>
        <p className="muted small">{t.adviceSource}</p>
      </section>
      <Followup output={output} />
      <CallNowCard />
      <TextButton onClick={() => navigate('/navigator')}>{t.askNavigator}</TextButton>
      <DoneButton />
    </main>
  );
}

function WarningResult({ output }: { output: TriageOutput }) {
  const { t, lang, locale, now, contacts } = useApp();
  const level = output.uroven;
  const meta = TRIAGE_LEVELS[level];
  return (
    <main className="content result">
      <section className="level-card" data-level={level}>
        <span className="level-title">
          <SvgIcon svg={meta.icon} />
          {lang === 'sk' ? `${meta.sk} · ${meta.stepSk}` : `${meta.cs} · ${meta.stepCs}`}
        </span>
        <p className="level-text">{output.doporuceni_pro_pacienta}</p>
      </section>
      <section className="card">
        <h2 className="card-title">{t.nextStep}</h2>
        {output.doporuceny_kontakt && <p className="strong">{capitalize(output.doporuceny_kontakt)}</p>}
        {output.sla_do && <p className="muted">{format(t.deadline, formatDayTime(new Date(output.sla_do), locale).toLowerCase())}</p>}
        {output.upozornit_tym && (
          <p className="ok-line">
            <SvgIcon svg={checkCircleIcon} />
            {t.teamNotified}
          </p>
        )}
        <CallButtons targets={callTargets(level, now, contacts, t)} />
      </section>
      <Followup output={output} />
      <CallNowCard />
      <DoneButton />
    </main>
  );
}

function usePhoneScript(output: TriageOutput, checkin: CheckinInput | undefined) {
  const { t, locale, patient, caregiver, forWhom } = useApp();
  const intro = caregiver ? format(t.phoneCaregiver, forWhom) : t.phoneSelf;
  const treatment = patient
    ? `: ${shortRegimen(patient.regimen)}${patient.cycle && patient.cycle_day ? `, ${format(t.phoneCycle, patient.cycle, patient.cycle_day)}` : ''}`
    : '';
  const vitals = checkin?.vitalni_funkce ?? {};
  const label = (key: VitalKey) => t[`vital_${key}`].charAt(0).toLowerCase() + t[`vital_${key}`].slice(1);
  const unit = (key: VitalKey) => VITALS.find((vital) => vital.key === key)!.unit;
  const measured = (['teplota_c', 'tk_sys', 'tepova_frekvence', 'spo2', 'dechova_frekvence'] as const)
    .filter((key) => vitals[key])
    .map((key) =>
      key === 'tk_sys' && vitals.tk_dia
        ? `${label(key).split(' ')[0]} ${vitals.tk_sys.hodnota}/${vitals.tk_dia.hodnota} ${unit(key)}`
        : `${label(key)} ${vitals[key].hodnota.toLocaleString(locale)} ${unit(key)}`,
    )
    .join(', ');
  const words = (checkin?.zprava_pacienta || output.dukazy.map((evidence) => evidence.citace).slice(0, 2).join('; ')).replace(/[.!?\s]+$/, '');
  return [`${intro}${treatment}.`, measured && format(t.phoneMeasured, measured), words && format(t.phoneHas, words)].filter(Boolean).join(' ');
}

function RedResult({ output, checkin }: { output: TriageOutput; checkin?: CheckinInput }) {
  const { t, lang, now, contacts } = useApp();
  const navigate = useNavigate();
  const script = usePhoneScript(output, checkin);
  const [primary, ...others] = callTargets(4, now, contacts, t);
  const meta = TRIAGE_LEVELS[4];
  return (
    <main className="red-screen">
      <header className="red-header">
        <span className="red-label">
          <SvgIcon svg={emergencyIcon} />
          {lang === 'sk' ? `${meta.sk} · ${meta.stepSk}` : `${meta.cs} · ${meta.stepCs}`}
        </span>
        <h1 className="headline">{t.redTitle}</h1>
        <p>{output.doporuceni_pro_pacienta}</p>
      </header>
      <div className="content">
        <p className="ok-line">
          <SvgIcon svg={checkCircleIcon} />
          {t.teamNotifiedRed}
        </p>
        <a className="call-big" href={`tel:${phoneDigits(primary.tel)}`}>
          <SvgIcon svg={callIcon} />
          <span>
            <strong>{primary.label}</strong>
            <span>{t.call155Sub}</span>
          </span>
        </a>
        {others.map((target) => (
          <CallButton key={target.tel} target={target} />
        ))}
        <section className="card">
          <h2 className="card-title">{t.phoneScriptTitle}</h2>
          <p className="script">„{script}“</p>
        </section>
        <p className="muted">{t.dontWait}</p>
        <TextButton onClick={() => navigate('/')}>{t.toHome}</TextButton>
      </div>
    </main>
  );
}

function QueuedResult() {
  const { t } = useApp();
  return (
    <main className="content result">
      <span className="result-icon">
        <SvgIcon svg={wifiOffIcon} />
      </span>
      <h1 className="headline">{t.queuedTitle}</h1>
      <p>{t.queuedText}</p>
      <CallNowCard />
      <DoneButton />
    </main>
  );
}
