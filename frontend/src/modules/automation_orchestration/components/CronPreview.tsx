import { useMemo } from "react";

function matchesPart(part: string, value: number, min: number, max: number): boolean {
  return part.split(",").some((segment) => {
    const [range = "", stepText] = segment.split("/");
    const step = stepText ? Number(stepText) : 1;
    if (!Number.isInteger(step) || step < 1) return false;
    if (range === "*") return (value - min) % step === 0;
    if (range.includes("-")) {
      const [startText, endText] = range.split("-");
      const start = Number(startText);
      const end = Number(endText);
      return Number.isInteger(start) && Number.isInteger(end) && start >= min && end <= max && value >= start && value <= end && (value - start) % step === 0;
    }
    return Number(range) === value;
  });
}

// Utility is intentionally colocated with the preview to keep cron semantics identical.
// eslint-disable-next-line react-refresh/only-export-components
export function nextCronRuns(
  expression: string,
  timezone: string,
  count = 5,
  searchHorizonDays = 366,
): readonly Date[] {
  const fields = expression.trim().split(/\s+/);
  if (fields.length !== 5) return [];
  const [minute = "", hour = "", day = "", month = "", weekday = ""] = fields;
  const formatter = new Intl.DateTimeFormat("en-US", { timeZone: timezone, minute: "numeric", hour: "numeric", hourCycle: "h23", day: "numeric", month: "numeric", weekday: "short" });
  const weekdayNumber: Readonly<Record<string, number>> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
  const runs: Date[] = [];
  const candidate = new Date();
  candidate.setSeconds(0, 0);
  candidate.setMinutes(candidate.getMinutes() + 1);
  const searchHorizonMinutes = searchHorizonDays * 24 * 60;
  for (let checked = 0; checked < searchHorizonMinutes && runs.length < count; checked += 1) {
    const parts = formatter.formatToParts(candidate);
    const find = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value ?? "";
    const dow = weekdayNumber[find("weekday")];
    if (dow !== undefined && matchesPart(minute, Number(find("minute")), 0, 59) && matchesPart(hour, Number(find("hour")), 0, 23) && matchesPart(day, Number(find("day")), 1, 31) && matchesPart(month, Number(find("month")), 1, 12) && matchesPart(weekday, dow, 0, 6)) runs.push(new Date(candidate));
    candidate.setMinutes(candidate.getMinutes() + 1);
  }
  return runs;
}

export function CronPreview({
  expression,
  timezone,
  count,
  searchHorizonDays,
}: {
  expression: string;
  timezone: string;
  count: number;
  searchHorizonDays: number;
}) {
  const preview = useMemo(() => {
    try { return nextCronRuns(expression, timezone, count, searchHorizonDays); } catch { return []; }
  }, [count, expression, searchHorizonDays, timezone]);
  return (
    <div className="rounded-lg border bg-muted/30 p-4">
      <p className="text-sm font-medium">Upcoming scheduled times</p>
      {preview.length === 0 ? <p className="mt-2 text-sm text-destructive">Enter a valid five-field cron expression and IANA timezone.</p> : <ol className="mt-3 space-y-1 text-sm text-muted-foreground">{preview.map((date) => <li key={date.toISOString()}>{new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "long", timeZone: timezone }).format(date)}</li>)}</ol>}
    </div>
  );
}
