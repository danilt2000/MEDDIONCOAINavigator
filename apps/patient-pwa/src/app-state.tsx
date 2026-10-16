import {
  api,
  ApiError,
  type CheckinInput,
  type Contacts,
  type DemoState,
  type Level,
  type PatientDetail,
  type PatientListItem,
  type TriageOutput,
} from '@navigator/api';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { dictionaries, format, type Dict } from './i18n';

export const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? fallback : (JSON.parse(raw) as T);
    } catch {
      return fallback;
    }
  },
  set(key: string, value: unknown) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // storage blocked or full: the app still works without it
    }
  },
};

interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
}

export function useApi<T>(path: string | null, refreshKey?: unknown) {
  const [state, setState] = useState<ApiState<T>>({ data: null, error: null, loading: !!path });
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setState((previous) => ({ ...previous, data: store.get<T | null>(`cache:${path}`, null), loading: true }));
    api
      .get<T>(path)
      .then((data) => {
        if (cancelled) return;
        store.set(`cache:${path}`, data);
        setState({ data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState((previous) => ({ ...previous, error: String(error), loading: false }));
      });
    return () => {
      cancelled = true;
    };
  }, [path, tick, refreshKey]);
  const reload = useCallback(() => setTick((value) => value + 1), []);
  return { ...state, reload };
}

const QUEUE_KEY = 'queue:checkins';
const PRAGUE = 'Europe/Prague';

export async function submitCheckin(checkin: CheckinInput, now: Date): Promise<TriageOutput | 'queued'> {
  try {
    const output = await api.post<TriageOutput>('/api/checkins', checkin);
    store.set(`last:${output.patient_id}`, output);
    return output;
  } catch (error) {
    if (error instanceof ApiError && error.status < 500) throw error;
    const [datum, cas] = new Intl.DateTimeFormat('sv-SE', { timeZone: PRAGUE, dateStyle: 'short', timeStyle: 'short' })
      .format(now)
      .split(' ');
    store.set(QUEUE_KEY, [...store.get<CheckinInput[]>(QUEUE_KEY, []), { ...checkin, datum, cas }]);
    return 'queued';
  }
}

let flushing = false;

async function flushQueue(): Promise<{ remaining: number; delivered: TriageOutput[] }> {
  const queue = store.get<CheckinInput[]>(QUEUE_KEY, []);
  if (!queue.length || flushing) return { remaining: queue.length, delivered: [] };
  flushing = true;
  const remaining: CheckinInput[] = [];
  const delivered: TriageOutput[] = [];
  for (const checkin of queue) {
    try {
      const output = await api.post<TriageOutput>('/api/checkins', checkin);
      store.set(`last:${output.patient_id}`, output);
      delivered.push(output);
    } catch (error) {
      // ponytail: a 4xx (invalid payload) is dropped instead of retried forever
      if (!(error instanceof ApiError && error.status < 500)) remaining.push(checkin);
    }
  }
  const added = store.get<CheckinInput[]>(QUEUE_KEY, []).slice(queue.length);
  store.set(QUEUE_KEY, [...remaining, ...added]);
  flushing = false;
  return { remaining: remaining.length + added.length, delivered };
}

export function pragueClock(date: Date) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: PRAGUE,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? '';
  return { weekday: part('weekday'), minutes: Number(part('hour')) * 60 + Number(part('minute')) };
}

export function inWorkingHours(date: Date) {
  const { weekday, minutes } = pragueClock(date);
  return !['Sat', 'Sun'].includes(weekday) && minutes >= 7 * 60 && minutes < 15 * 60 + 30;
}

export const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);

export const formatDay = (date: Date, locale: string) =>
  capitalize(new Intl.DateTimeFormat(locale, { timeZone: PRAGUE, weekday: 'long', day: 'numeric', month: 'numeric' }).format(date));

export const formatTime = (date: Date, locale: string) =>
  new Intl.DateTimeFormat(locale, { timeZone: PRAGUE, hour: '2-digit', minute: '2-digit' }).format(date);

export const formatDayTime = (date: Date, locale: string) => `${formatDay(date, locale)} ${formatTime(date, locale)}`;

export const sameDay = (a: Date, b: Date) =>
  new Intl.DateTimeFormat('en-CA', { timeZone: PRAGUE }).format(a) === new Intl.DateTimeFormat('en-CA', { timeZone: PRAGUE }).format(b);

export const phoneDigits = (phone: string) => phone.replace(/[^\d+]/g, '');
export const formatPhone = (phone: string) => phoneDigits(phone).replace(/(\d{3})(?=\d)/g, '$1 ');

export const shortRegimen = (regimen: string) => regimen.split(/\s\(|\sà|,|;/)[0].trim();

export function nextApplication(now: Date, regimen: string, cycleDay: number | null): Date | null {
  // ponytail: cycle length parsed from "à 21 dní" in the regimen text; use the CarePlan when the API exposes it
  const cycleLength = Number(/à\s*(\d+)\s*dn/.exec(regimen)?.[1]);
  if (!cycleLength || !cycleDay) return null;
  return new Date(now.getTime() + (cycleLength - cycleDay + 1) * 86_400_000);
}

export interface CallTarget {
  label: string;
  tel: string;
  strong?: boolean;
}

export function callTargets(level: Level, now: Date, contacts: Contacts | null, t: Dict): CallTarget[] {
  const ems = contacts?.ems.phone || '155';
  const onDuty = contacts?.on_duty.phone || '724590848';
  const centre = contacts?.monitoring_centre.phone;
  const hours = inWorkingHours(now);
  const emsTarget = { label: t.call155, tel: ems };
  const onDutyTarget = { label: `${t.callOnDuty}: ${formatPhone(onDuty)}`, tel: onDuty };
  const centreTarget = centre ? { label: `${t.callMc}: ${formatPhone(centre)}`, tel: centre } : null;
  if (level === 4) return [{ ...emsTarget, strong: true }, onDutyTarget];
  if (level === 3) return [{ ...(hours && centreTarget ? centreTarget : onDutyTarget), strong: true }, emsTarget];
  if (level === 2) {
    return hours && centreTarget
      ? [{ ...centreTarget, strong: true }, emsTarget]
      : [{ ...onDutyTarget, label: format(t.ifWorse, formatPhone(onDuty)) }, emsTarget];
  }
  return [];
}

export function ambulancePhone(now: Date, contacts: Contacts | null) {
  const onDuty = contacts?.on_duty.phone || '724590848';
  return inWorkingHours(now) ? contacts?.monitoring_centre.phone || onDuty : onDuty;
}

const RELATIONS = ['dcera', 'syn', 'manželka', 'manžel', 'vnučka', 'vnuk', 'partnerka', 'partner'];

const relationOf = (filledBy: string) => RELATIONS.find((relation) => filledBy.toLowerCase().includes(relation)) ?? 'pecujici';

function forWhomLabel(relation: string, sex: string, name: string, t: Dict) {
  if (['dcera', 'syn', 'vnučka', 'vnuk'].includes(relation)) return sex === 'F' ? t.mother : t.father;
  if (relation === 'manželka') return t.husband;
  if (relation === 'manžel') return t.wife;
  return name;
}

interface AppValue {
  patientId: string;
  setPatientId: (id: string) => void;
  patients: PatientListItem[];
  patient: PatientListItem | PatientDetail | null;
  patientError: string | null;
  t: Dict;
  lang: 'cs' | 'sk';
  locale: string;
  now: Date;
  demo: DemoState | null;
  contacts: Contacts | null;
  caregiver: boolean;
  setCaregiver: (on: boolean) => void;
  relation: string;
  forWhom: string;
  online: boolean;
  queued: number;
  refreshQueue: () => void;
}

const AppContext = createContext<AppValue | null>(null);

export const useApp = () => useContext(AppContext)!;

function initialPatientId() {
  const fromUrl = new URLSearchParams(location.search).get('patient');
  if (fromUrl) store.set('patient', fromUrl);
  return fromUrl ?? store.get('patient', 'ONC-001');
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [patientId, setPatientIdState] = useState(initialPatientId);
  const [poll, setPoll] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);
  const [queued, setQueued] = useState(() => store.get<CheckinInput[]>(QUEUE_KEY, []).length);
  const [caregiverOverride, setCaregiverOverride] = useState<boolean | null>(() => store.get(`caregiver:${patientId}`, null));

  const patients = useApi<PatientListItem[]>('/api/patients');
  const detail = useApi<PatientDetail>(`/api/patients/${patientId}`);
  const demo = useApi<DemoState>('/api/demo/state', poll);
  const contacts = useApi<Contacts>('/api/contacts');
  useApi<unknown>('/api/questionnaires');
  const navigate = useNavigate();
  const currentPatient = useRef(patientId);
  currentPatient.current = patientId;

  useEffect(() => {
    const timer = setInterval(() => setPoll((value) => value + 1), 30_000);
    return () => clearInterval(timer);
  }, []);

  const refreshQueue = useCallback(() => {
    flushQueue().then(({ remaining, delivered }) => {
      setQueued(remaining);
      const mine = delivered.filter((output) => output.patient_id === currentPatient.current).pop();
      if (mine && location.pathname !== '/checkin') navigate('/vysledek', { state: { output: mine } });
    }, () => undefined);
  }, [navigate]);

  useEffect(() => {
    const timer = setInterval(refreshQueue, 15_000);
    return () => clearInterval(timer);
  }, [refreshQueue]);

  useEffect(() => {
    const goOnline = () => {
      setOnline(true);
      refreshQueue();
    };
    const goOffline = () => setOnline(false);
    addEventListener('online', goOnline);
    addEventListener('offline', goOffline);
    refreshQueue();
    return () => {
      removeEventListener('online', goOnline);
      removeEventListener('offline', goOffline);
    };
  }, [refreshQueue]);

  const value = useMemo<AppValue>(() => {
    const patient = detail.data ?? patients.data?.find((item) => item.patient_id === patientId) ?? null;
    const lang = patient?.lang === 'sk' ? 'sk' : 'cs';
    const t = dictionaries[lang];
    const filledBy = patient?.filled_by ?? '';
    const relation = relationOf(filledBy);
    const caregiverDefault = /^(peč|pec)/i.test(filledBy.trim());
    return {
      patientId,
      setPatientId: (id: string) => {
        store.set('patient', id);
        const url = new URL(location.href);
        url.searchParams.set('patient', id);
        history.replaceState(history.state, '', url);
        setPatientIdState(id);
        setCaregiverOverride(store.get(`caregiver:${id}`, null));
      },
      patients: patients.data ?? [],
      patient,
      patientError: patient ? null : detail.error,
      t,
      lang,
      locale: lang === 'sk' ? 'sk-SK' : 'cs-CZ',
      now: demo.data?.now ? new Date(demo.data.now) : new Date(),
      demo: demo.data,
      contacts: contacts.data,
      caregiver: caregiverOverride ?? caregiverDefault,
      setCaregiver: (on: boolean) => {
        store.set(`caregiver:${patientId}`, on);
        setCaregiverOverride(on);
      },
      relation,
      forWhom: forWhomLabel(relation, patient?.sex ?? '', patient?.name ?? '', t),
      online,
      queued,
      refreshQueue,
    };
  }, [patientId, patients.data, detail.data, detail.error, demo.data, contacts.data, caregiverOverride, online, queued, refreshQueue]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
