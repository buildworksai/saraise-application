import { useAuthStore } from '@/stores/auth-store';

export function useCanManageProcessMining(): boolean {
  return useAuthStore((state) => [state.user?.is_superuser, state.user?.tenant_role === 'tenant_admin'].some(Boolean));
}

export function deterministicKey(...parts: readonly string[]): string {
  return `process-mining:${parts.map((part) => encodeURIComponent(part.trim().toLowerCase())).join(':')}`;
}

export function formatDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : '—';
}

export function formatDuration(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const seconds = Number(value);
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function toLocalInput(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
