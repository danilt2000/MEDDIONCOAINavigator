import { ApiError, api } from '@navigator/api';
import { useEffect, useState } from 'react';

export interface Loadable<T> {
  data: T | undefined;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404) return 'Data zatím nejsou k dispozici (404).';
    return `Server odpověděl chybou ${error.status}.`;
  }
  return 'Server je nedostupný.';
}

export function useApi<T>(path: string | null, refreshMs?: number): Loadable<T> {
  const [state, setState] = useState<{ path: string | null; data?: T; error: string | null; loading: boolean }>({
    path: null,
    error: null,
    loading: true,
  });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    setState((previous) => (previous.path === path ? { ...previous, loading: true } : { path, error: null, loading: true }));
    api.get<T>(path).then(
      (data) => !cancelled && setState({ path, data, error: null, loading: false }),
      (error) =>
        !cancelled &&
        setState((previous) => ({ path, data: previous.path === path ? previous.data : undefined, error: errorText(error), loading: false })),
    );
    return () => {
      cancelled = true;
    };
  }, [path, tick]);

  useEffect(() => {
    if (!refreshMs) return;
    const id = setInterval(() => setTick((value) => value + 1), refreshMs);
    return () => clearInterval(id);
  }, [refreshMs]);

  const current = state.path === path;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : null,
    loading: !current || state.loading,
    reload: () => setTick((value) => value + 1),
  };
}

export function useNow(offsetMs: number, everyMs = 1000): number {
  const [now, setNow] = useState(() => Date.now() + offsetMs);
  useEffect(() => {
    setNow(Date.now() + offsetMs);
    const id = setInterval(() => setNow(Date.now() + offsetMs), everyMs);
    return () => clearInterval(id);
  }, [offsetMs, everyMs]);
  return now;
}

const TZ = 'Europe/Prague';
const dayFormat = new Intl.DateTimeFormat('cs-CZ', { timeZone: TZ, weekday: 'short', day: 'numeric', month: 'numeric' });
const timeFormat = new Intl.DateTimeFormat('cs-CZ', { timeZone: TZ, hour: '2-digit', minute: '2-digit' });
const isoDayFormat = new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' });
const partsFormat = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

const toDate = (value: string | number | Date) => (value instanceof Date ? value : new Date(value));

export const fmtDay = (value: string | number | Date) => dayFormat.format(toDate(value));
export const fmtTime = (value: string | number | Date) => timeFormat.format(toDate(value));
export const fmtDayTime = (value: string | number | Date) => `${fmtDay(value)} ${fmtTime(value)}`;
export const isoDay = (value: string | number | Date) => isoDayFormat.format(toDate(value));

export function pragueClock(value: string | number | Date): { weekday: number; minutes: number } {
  const parts = Object.fromEntries(partsFormat.formatToParts(toDate(value)).map((part) => [part.type, part.value]));
  const weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(parts.weekday);
  return { weekday, minutes: Number(parts.hour) * 60 + Number(parts.minute) };
}

export const WORK_START = 7 * 60;
export const WORK_END = 15 * 60 + 30;

export function inWorkingHours(value: string | number | Date): boolean {
  const { weekday, minutes } = pragueClock(value);
  return weekday >= 1 && weekday <= 5 && minutes >= WORK_START && minutes < WORK_END;
}

export function addDays(day: string, days: number): string {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function daysBetween(from: string, to: string): string[] {
  const days: string[] = [];
  for (let day = from; day <= to && days.length < 400; day = addDays(day, 1)) days.push(day);
  return days;
}

export function fmtDuration(ms: number): string {
  const totalMinutes = Math.floor(Math.abs(ms) / 60000);
  if (totalMinutes < 60) {
    const seconds = Math.floor((Math.abs(ms) % 60000) / 1000);
    return `${totalMinutes}:${String(seconds).padStart(2, '0')} min`;
  }
  const hours = Math.floor(totalMinutes / 60);
  if (hours < 24) return `${hours} h ${totalMinutes % 60} min`;
  return `${Math.floor(hours / 24)} d ${hours % 24} h`;
}

export function fmtMinutesAgo(fromIso: string, now: number): string {
  const minutes = Math.max(0, Math.round((now - new Date(fromIso).getTime()) / 60000));
  if (minutes < 120) return `${minutes} min`;
  if (minutes < 48 * 60) return `${Math.round(minutes / 60)} h`;
  return `${Math.round(minutes / 1440)} d`;
}

export function shortRegimen(regimen: string): string {
  const head = regimen
    .replace(/\s*\([^)]*\)/g, '')
    .split(/ à |, |;/)[0]
    .trim();
  return head.length > 42 ? `${head.slice(0, 40)}…` : head;
}

export const TASK_STATUS: Record<string, string> = {
  requested: 'Čeká na převzetí',
  accepted: 'Převzato',
  'in-progress': 'Řeší se',
  completed: 'Uzavřeno',
};

export function beep() {
  try {
    const context = new AudioContext();
    [0, 0.35].forEach((start) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.25, context.currentTime + start);
      gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + start + 0.3);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(context.currentTime + start);
      oscillator.stop(context.currentTime + start + 0.3);
    });
  } catch {
    /* audio blocked until the first user interaction */
  }
}
