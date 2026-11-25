import { formatClock, formatUtc } from "../time";

export interface TimeProps {
  at: number;
  /** The reference "now" for whether to show the date; defaults to the clock. */
  now?: number | undefined;
  /** For tests; the page uses the viewer's own zone. */
  timeZone?: string | undefined;
}

/** A time in the viewer's zone, with UTC on hover (plan §4). */
export function Time({ at, now, timeZone }: TimeProps) {
  return (
    <time dateTime={new Date(at).toISOString()} title={formatUtc(at)}>
      {formatClock(at, now ?? Date.now(), timeZone)}
    </time>
  );
}
