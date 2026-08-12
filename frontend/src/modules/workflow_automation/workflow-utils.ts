export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatDuration(
  start: string | null,
  end: string | null,
  minuteThresholdMs: number
): string {
  if (!start) return "—";
  if (!Number.isFinite(minuteThresholdMs) || minuteThresholdMs <= 0) return "—";
  const startTime = new Date(start).getTime();
  const endTime = end ? new Date(end).getTime() : Date.now();
  if (Number.isNaN(startTime) || Number.isNaN(endTime)) return "—";
  const milliseconds = Math.max(0, endTime - startTime);
  if (milliseconds < minuteThresholdMs) return `${Math.floor(milliseconds / 1000)}s`;
  return `${Math.floor(milliseconds / minuteThresholdMs)}m ${Math.round((milliseconds % minuteThresholdMs) / 1000)}s`;
}

export function newTransitionKey(prefix: string): string {
  return `${prefix}:${crypto.randomUUID()}`;
}
