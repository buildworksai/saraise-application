import { useEffect } from 'react';

export function useRegionalDocumentTitle(title: string): void {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = `${title} · SARAISE`;
    return () => {
      document.title = previousTitle;
    };
  }, [title]);
}
