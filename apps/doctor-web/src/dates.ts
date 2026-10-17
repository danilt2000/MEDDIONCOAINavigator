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

export const isIsoDay = (day: string) => /^\d{4}-\d{2}-\d{2}$/.test(day) && !Number.isNaN(Date.parse(day)) && addDays(day, 0) === day;

export const fmtTimeOrDayTime = (value: string, sameDayAs: string | null | undefined) =>
  sameDayAs && isoDay(value) === isoDay(sameDayAs) ? fmtTime(value) : fmtDayTime(value);
