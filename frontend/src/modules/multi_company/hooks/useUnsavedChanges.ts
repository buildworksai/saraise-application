import { useEffect } from 'react';

/** Protect in-progress financial and configuration input from accidental reloads. */
export function useUnsavedChanges(dirty: boolean): void {
  useEffect(() => {
    const handle = (event: BeforeUnloadEvent) => { if (dirty) event.preventDefault(); };
    window.addEventListener('beforeunload', handle);
    return () => window.removeEventListener('beforeunload', handle);
  }, [dirty]);
}
