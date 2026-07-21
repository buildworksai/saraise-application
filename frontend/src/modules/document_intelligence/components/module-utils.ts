import { useEffect } from 'react';
import { useAuthStore } from '@/stores/auth-store';

export function useCanManageDocumentIntelligence(): boolean {
  return useAuthStore((state) => state.user?.tenant_role === 'tenant_admin');
}

export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);
}

export function formatConfidence(value: string | null): string {
  return value === null ? '—' : `${Math.round(Number(value) * 100)}%`;
}

export function deterministicKey(...parts: readonly string[]): string {
  return `document-intelligence:${parts.map((part) => encodeURIComponent(part.trim().toLowerCase())).join(':')}`;
}

export function stableFingerprint(value: string): string {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}
