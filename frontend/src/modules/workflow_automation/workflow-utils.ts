export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

export function formatDuration(start: string | null, end: string | null, minuteThresholdMs: number): string {
  if (!start) return "—";
  const milliseconds = Math.max(0, new Date(end ?? Date.now()).getTime() - new Date(start).getTime());
  if (milliseconds < minuteThresholdMs) return `${Math.round(milliseconds / 1000)}s`;
  return `${Math.floor(milliseconds / minuteThresholdMs)}m ${Math.round((milliseconds % minuteThresholdMs) / 1000)}s`;
}

export function newTransitionKey(prefix: string): string {
  return `${prefix}:${crypto.randomUUID()}`;
}
