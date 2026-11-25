// Times show in the viewer's time zone, on a 24-hour clock, with UTC on hover (master plan §4).

const clockFormats = new Map<string, Intl.DateTimeFormat>();
const dayFormats = new Map<string, Intl.DateTimeFormat>();
const dateFormats = new Map<string, Intl.DateTimeFormat>();

function cached(cache: Map<string, Intl.DateTimeFormat>, zone: string | undefined, options: Intl.DateTimeFormatOptions) {
  const key = zone ?? "";
  let format = cache.get(key);
  if (!format) {
    format = new Intl.DateTimeFormat("en-GB", zone ? { ...options, timeZone: zone } : options);
    cache.set(key, format);
  }
  return format;
}

const CLOCK: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hourCycle: "h23" };
const DAY: Intl.DateTimeFormatOptions = { year: "numeric", month: "2-digit", day: "2-digit" };
const DATE: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" };

/**
 * "14:02" in the viewer's zone; "24 Nov 23:50" when that is not the same day as `now` there.
 * `timeZone` is for tests; the page leaves it out and gets the browser's own zone.
 */
export function formatClock(at: number, now: number, timeZone?: string): string {
  const clock = cached(clockFormats, timeZone, CLOCK).format(at);
  const day = cached(dayFormats, timeZone, DAY);
  if (day.format(at) === day.format(now)) return clock;
  return `${cached(dateFormats, timeZone, DATE).format(at)} ${clock}`;
}

/** "2026-11-25 14:02 UTC": what hover shows. */
export function formatUtc(at: number): string {
  const iso = new Date(at).toISOString();
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

/** "14:02" in UTC, for copy that says "UTC" itself. */
export function formatUtcClock(at: number): string {
  return new Date(at).toISOString().slice(11, 16);
}
