import { useEffect, useState } from 'react';
export type FormErrors = Record<string, string>;
export function useDirtyGuard(initiallyDirty = false) {
  const [dirty, setDirty] = useState(initiallyDirty);
  useEffect(() => { const handler = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); }; window.addEventListener('beforeunload', handler); return () => window.removeEventListener('beforeunload', handler); }, [dirty]);
  return { dirty, markDirty: () => setDirty(true), markClean: () => setDirty(false) };
}
export const isoToday = () => new Date().toISOString().slice(0, 10);
export const validEmail = (value: string) => /^\S+@\S+\.\S+$/u.test(value);
export const value = (data: FormData, key: string) => { const entry = data.get(key); return typeof entry === 'string' ? entry.trim() : ''; };
