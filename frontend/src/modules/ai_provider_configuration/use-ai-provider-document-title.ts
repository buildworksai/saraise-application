import { useEffect } from 'react';

export function useAiProviderDocumentTitle(title: string) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} | SARAISE`;
    return () => {
      document.title = previous;
    };
  }, [title]);
}
