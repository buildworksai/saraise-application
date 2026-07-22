import { useEffect, useState } from "react";

interface SavedView { readonly name: string; readonly query: string; }
function isSavedView(value: unknown): value is SavedView { return Boolean(value && typeof value === "object" && "name" in value && "query" in value); }

export function useSavedViews(scope: string, currentQuery: string) {
  const storageKey = `saraise.mdm.saved-view.${scope}`;
  const [views, setViews] = useState<readonly SavedView[]>([]);
  useEffect(() => { const saved = localStorage.getItem(storageKey); if (!saved) return; try { const parsed: unknown = JSON.parse(saved); if (Array.isArray(parsed)) setViews(parsed.filter(isSavedView)); } catch { localStorage.removeItem(storageKey); } }, [storageKey]);
  const save = (name: string) => { const next = [...views.filter((view) => view.name !== name), { name, query: currentQuery }]; localStorage.setItem(storageKey, JSON.stringify(next)); setViews(next); };
  const remove = (name: string) => { const next = views.filter((view) => view.name !== name); localStorage.setItem(storageKey, JSON.stringify(next)); setViews(next); };
  return { views, save, remove };
}
