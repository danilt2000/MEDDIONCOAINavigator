import checkCircleIcon from '@material-symbols/svg-400/outlined/check_circle.svg?raw';
import type { CheckinInput, QuestionnaireDefinition, TriageOutput } from '@navigator/api';
import { FilledButton, LinearProgress, OutlinedTextField, SvgIcon, Switch, TextButton, TriageChip } from '@navigator/ui';
import { useEffect, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { checkinDraft, formatTime, sameDay, store, submitCheckin, useApi, useApp } from '../app-state';
import {
  answerKey,
  buildFills,
  buildVitals,
  hasValue,
  optionColor,
  parseVital,
  scaleColor,
  toggleOption,
  treatmentReason,
  visibleSteps,
  VITALS,
  type Answers,
  type Item,
  type Questionnaire,
  type Value,
  UNKNOWN,
  type VitalKey,
} from '../flow';
import { format } from '../i18n';
import { AcuteButton, AiFab, AmbulanceAnd155, BackButton, ErrorBanner } from '../ui';

const fieldValue = (event: Event) => (event.target as HTMLInputElement).value;

type Vitals = Partial<Record<VitalKey, string>>;

function pickQuestionnaires(all: Questionnaire[], badges: string[]) {
  const wanted = ['nezadouci_ucinky'];
  if (badges.includes('paliativní')) wanted.push('esas');
  if (badges.includes('opioid')) wanted.push('bolest_analgeticka_terapie');
  return wanted.map((id) => all.find((questionnaire) => questionnaire.id === id)).filter((found) => !!found);
}

function useLastCheckin() {
  const { patientId } = useApp();
  const triage = useApi<TriageOutput[]>(`/api/patients/${patientId}/triage`);
  const stored = store.get<TriageOutput | null>(`last:${patientId}`, null);
  const fromApi = triage.data?.find((output) => output.zdroj !== 'chat') ?? null;
  return !stored || (fromApi && fromApi.as_of >= stored.as_of) ? fromApi : stored;
}

function QuestionInput(props: { questionnaireId: string; item: Item; value: Value | undefined; onChange: (value: Value | undefined) => void }) {
  const { questionnaireId, item, value, onChange } = props;
  const { t } = useApp();
  const options = item.moznosti ?? [];
  if (item.typ === 'jedna') {
    return (
      <div className="options" role="radiogroup" aria-labelledby="question">
        <label className="option" data-barva="nevim">
          <input
            type="radio"
            name={item.id}
            checked={value === undefined || value === UNKNOWN}
            onChange={() => onChange(UNKNOWN)}
            onClick={() => onChange(UNKNOWN)}
          />
          <span>{t.dontKnowAnswer}</span>
        </label>
        {options.map((option, index) => (
          <label key={option.text} className="option" data-barva={optionColor(item, index) ?? undefined}>
            <input type="radio" name={item.id} checked={value === index} onChange={() => onChange(index)} />
            <span>{option.text}</span>
          </label>
        ))}
      </div>
    );
  }
  if (item.typ === 'vice') {
    const selected = Array.isArray(value) ? value : [];
    return (
      <div className="options" role="group" aria-labelledby="question">
        {options.map((option, index) => (
          <label key={option.text} className="option" data-barva={optionColor(item, index) ?? undefined}>
            <input
              type="checkbox"
              checked={selected.includes(index)}
              onChange={() => onChange(toggleOption(item, selected, index))}
            />
            <span>{option.text}</span>
          </label>
        ))}
      </div>
    );
  }
  if (item.typ === 'skala_1_10') {
    return (
      <>
        <div className="scale" role="radiogroup" aria-labelledby="question">
          {Array.from({ length: 10 }, (_, index) => index + 1).map((score) => (
            <label key={score} className="option scale-option" data-barva={scaleColor(questionnaireId, item.id, score) ?? undefined}>
              <input type="radio" name={item.id} checked={value === score} onChange={() => onChange(score)} />
              <span>{score}</span>
            </label>
          ))}
        </div>
        <p className="muted small">{t.scaleHint}</p>
      </>
    );
  }
  if (item.typ === 'cislo') {
    return (
      <OutlinedTextField
        label={t.numberLabel}
        type="number"
        inputMode="numeric"
        min="0"
        value={value === undefined ? '' : String(value)}
        onInput={(event) => {
          const number = Number.parseInt(fieldValue(event), 10);
          onChange(Number.isNaN(number) ? undefined : number);
        }}
      />
    );
  }
  return (
    <OutlinedTextField
      label={t.textLabel}
      type="textarea"
      rows={3}
      value={typeof value === 'string' ? value : ''}
      onInput={(event) => onChange(fieldValue(event))}
    />
  );
}

export function Checkin() {
  const { t, lang, locale, now, patient, patientId, patientError, caregiver, setCaregiver, relation, refreshQueue } = useApp();
  const navigate = useNavigate();
  const definitions = useApi<QuestionnaireDefinition[]>('/api/questionnaires');
  const last = useLastCheckin();
  const doneToday = last && sameDay(new Date(last.as_of), now) ? last : null;
  const saved = checkinDraft.current?.patientId === patientId ? checkinDraft.current : null;
  const [answers, setAnswers] = useState<Answers>(saved?.answers ?? {});
  const [stepIndex, setStepIndex] = useState(saved?.stepIndex ?? 0);
  const [vitals, setVitals] = useState<Vitals>(saved?.vitals ?? {});
  const [message, setMessage] = useState(saved?.message ?? '');
  const [photo, setPhoto] = useState(saved?.photo ?? '');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkinDraft.current = { patientId, answers, stepIndex, vitals, message, photo };
  });

  const selected = pickQuestionnaires((definitions.data ?? []) as unknown as Questionnaire[], patient?.risk_badges ?? []);
  const steps = visibleSteps(selected, answers);
  const total = steps.length + 2;
  const step = steps[stepIndex];
  const treatmentText = [patient?.regimen ?? '', ...(patient && 'meds' in patient ? patient.meds.map((med) => med.lek) : [])].join(' ');

  const go = (index: number) => {
    setStepIndex(index);
    scrollTo(0, 0);
  };

  if (!selected.length) {
    return (
      <main className="content">
        <div className="toolbar">
          <span className="toolbar-end">
            <AcuteButton />
          </span>
        </div>
        {definitions.loading ? (
          <LinearProgress indeterminate />
        ) : (
          <>
            <ErrorBanner message={t.questionnairesError} onRetry={definitions.reload} />
            <AmbulanceAnd155 />
          </>
        )}
      </main>
    );
  }

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    const checkin: CheckinInput = {
      patient_id: patientId,
      stav: 'vyplneno',
      vyplnil: caregiver ? relation : 'pacient',
      cyklus: patient?.cycle ?? null,
      den_cyklu: patient?.cycle_day ?? null,
      dotazniky: buildFills(selected, answers, `${patientId}-APP${Date.now().toString(36).toUpperCase()}`),
      vitalni_funkce: buildVitals(vitals),
      zprava_pacienta: message.trim() || null,
      prilohy: photo.trim() ? [`foto.jpg – ${photo.trim()}`] : [],
    };
    try {
      const result = await submitCheckin(checkin, now);
      checkinDraft.current = null;
      if (result === 'queued') refreshQueue();
      navigate('/vysledek', { replace: true, state: result === 'queued' ? { queued: true } : { output: result, checkin } });
    } catch (submitError) {
      setError(`${t.submitError} ${String(submitError)}`);
      setSubmitting(false);
    }
  };

  const unsure = step?.item.typ === 'jedna' && answers[answerKey(step.questionnaire.id, step.item.id)] === UNKNOWN;
  const aiIntro = step && unsure ? format(t.aiIntro, step.item.text) : undefined;

  let body;
  if (step) {
    const key = answerKey(step.questionnaire.id, step.item.id);
    const value = answers[key];
    const setValue = (next: Value | undefined) =>
      setAnswers((previous) => {
        const copy = { ...previous };
        if (next === undefined) delete copy[key];
        else copy[key] = next;
        return copy;
      });
    const reason = treatmentReason(step.item.id, treatmentText);
    const skip = () => {
      setValue(undefined);
      go(stepIndex + 1);
    };
    body = (
      <>
        {selected.length > 1 && <p className="overline">{step.questionnaire.nazev}</p>}
        {reason && <p className="context-chip">{format(t.becauseOf, 'chemo' in reason ? t.chemo : reason.drug)}</p>}
        <h1 id="question" className="question">
          {step.item.text}
        </h1>
        {step.item.navod && <p className="muted">{step.item.navod}</p>}
        <QuestionInput questionnaireId={step.questionnaire.id} item={step.item} value={value} onChange={setValue} />
        <Footer
          hint={
            aiIntro && (
              <div className="ai-hint" role="status">
                <span>{t.aiHint}</span>
                <TextButton onClick={() => navigate('/navigator', { state: { intro: aiIntro, patientId } })}>{t.aiHintButton}</TextButton>
              </div>
            )
          }
          next={t.next}
          onNext={() => go(stepIndex + 1)}
          canContinue={step.item.typ === 'jedna' || hasValue(value)}
          skip={step.item.typ === 'jedna' ? undefined : t.skip}
          onSkip={skip}
        />
      </>
    );
  } else if (stepIndex === steps.length) {
    const invalid = VITALS.some((vital) => parseVital(vital.key, vitals[vital.key] ?? '') === 'invalid');
    body = (
      <>
        <h1 className="question">{t.vitalsTitle}</h1>
        <p className="muted">{t.vitalsHint}</p>
        <div className="vitals">
          {VITALS.map((vital) => {
            const isInvalid = parseVital(vital.key, vitals[vital.key] ?? '') === 'invalid';
            return (
              <OutlinedTextField
                key={vital.key}
                label={t[`vital_${vital.key}`]}
                suffixText={vital.unit}
                inputMode="decimal"
                value={vitals[vital.key] ?? ''}
                error={isInvalid}
                errorText={isInvalid ? t.vitalInvalid : ''}
                onInput={(event) => setVitals((previous) => ({ ...previous, [vital.key]: fieldValue(event) }))}
              />
            );
          })}
        </div>
        <Footer
          next={t.next}
          onNext={() => go(stepIndex + 1)}
          canContinue={!invalid}
          skip={t.vitalsSkip}
          onSkip={() => {
            setVitals({});
            go(stepIndex + 1);
          }}
        />
      </>
    );
  } else {
    body = (
      <>
        <h1 className="question">{t.messageTitle}</h1>
        <p className="muted">{t.messageHint}</p>
        <OutlinedTextField
          label={t.messageLabel}
          type="textarea"
          rows={4}
          value={message}
          onInput={(event) => setMessage(fieldValue(event))}
        />
        <OutlinedTextField
          label={t.photoLabel}
          placeholder={t.photoHint}
          value={photo}
          onInput={(event) => setPhoto(fieldValue(event))}
        />
        <label className="switch-row">
          <span>{t.caregiverSwitch}</span>
          <Switch selected={caregiver} onChange={(event) => setCaregiver((event.target as HTMLInputElement & { selected: boolean }).selected)} />
        </label>
        {error && <ErrorBanner message={error} onRetry={submit} />}
        <div className="footer">
          <FilledButton disabled={submitting} onClick={submit}>
            {submitting ? t.sending : t.submit}
          </FilledButton>
        </div>
      </>
    );
  }

  return (
    <main className="content checkin">
      <div className="toolbar">
        {stepIndex > 0 && <BackButton onClick={() => go(stepIndex - 1)} />}
        <span className="muted strong-ish">{format(t.questionOf, Math.min(stepIndex + 1, total), total)}</span>
        <span className="toolbar-end">
          <AcuteButton />
          <AiFab size="small" intro={aiIntro} />
        </span>
      </div>
      <LinearProgress value={Math.min(stepIndex + 1, total) / total} aria-label={format(t.questionOf, stepIndex + 1, total)} />
      {patientError && !patient && <ErrorBanner message={t.loadError} onRetry={() => location.reload()} />}
      {stepIndex === 0 && doneToday && (
        <button type="button" className="list-button done-today" onClick={() => navigate('/vysledek', { state: { output: doneToday } })}>
          <SvgIcon svg={checkCircleIcon} />
          <span>{format(t.todayDone, formatTime(new Date(doneToday.as_of), locale))}</span>
          <TriageChip level={doneToday.uroven} lang={lang} />
        </button>
      )}
      {body}
    </main>
  );
}

function Footer(props: { hint?: ReactNode; next: string; onNext: () => void; canContinue: boolean; skip?: string; onSkip: () => void }) {
  return (
    <div className="footer">
      {props.hint}
      <FilledButton disabled={!props.canContinue} onClick={props.onNext}>
        {props.next}
      </FilledButton>
      {props.skip && <TextButton onClick={props.onSkip}>{props.skip}</TextButton>}
    </div>
  );
}
