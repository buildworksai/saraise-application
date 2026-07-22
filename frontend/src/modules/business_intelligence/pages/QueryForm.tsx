import { useEffect, useMemo, useState } from "react";
import { CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui";
import type { DatasetDescriptor, QueryCreate } from "../contracts";
import { MutationError, UnsavedWarning } from "./shared";
// eslint-disable-next-line max-lines-per-function -- progressive semantic builder is one accessible form workflow
export function QueryForm({
  initial,
  datasets,
  dataset,
  onDatasetChange,
  onSubmit,
  error,
  pending,
  storageKey,
  submitLabel,
}: {
  initial: QueryCreate;
  datasets: DatasetDescriptor[];
  dataset?: DatasetDescriptor;
  onDatasetChange: (key: string) => void;
  onSubmit: (value: QueryCreate) => void;
  error: unknown;
  pending: boolean;
  storageKey: string;
  submitLabel: string;
}) {
  const [form, setForm] = useState<QueryCreate>(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      return saved ? (JSON.parse(saved) as QueryCreate) : initial;
    } catch {
      return initial;
    }
  });
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    if (dirty) localStorage.setItem(storageKey, JSON.stringify(form));
  }, [dirty, form, storageKey]);
  useEffect(() => {
    if (form.dataset_key) onDatasetChange(form.dataset_key);
  }, [form.dataset_key, onDatasetChange]);
  const toggle = (kind: "dimensions" | "measures", key: string) => {
    setDirty(true);
    if (kind === "dimensions")
      setForm((v) => ({
        ...v,
        dimensions: v.dimensions.includes(key)
          ? v.dimensions.filter((x) => x !== key)
          : [...v.dimensions, key],
      }));
    else
      setForm((v) => ({
        ...v,
        measures: v.measures.some((x) => x.key === key)
          ? v.measures.filter((x) => x.key !== key)
          : [...v.measures, { key }],
      }));
  };
  const valid = useMemo(
    () =>
      Boolean(
        form.query_code.trim() &&
          form.name.trim() &&
          form.dataset_key &&
          (form.dimensions.length || form.measures.length)
      ),
    [form]
  );
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <UnsavedWarning when={dirty && !pending} />
      <MutationError error={error} />
      <Card>
        <CardHeader>
          <CardTitle>1. Definition</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">
            Code
            <Input
              required
              maxLength={64}
              value={form.query_code}
              onChange={(e) => {
                setDirty(true);
                setForm({
                  ...form,
                  query_code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/gu, ""),
                });
              }}
            />
          </label>
          <label className="text-sm font-medium">
            Name
            <Input
              required
              value={form.name}
              onChange={(e) => {
                setDirty(true);
                setForm({ ...form, name: e.target.value });
              }}
            />
          </label>
          <label className="sm:col-span-2 text-sm font-medium">
            Description
            <Textarea
              value={form.description ?? ""}
              onChange={(e) => {
                setDirty(true);
                setForm({ ...form, description: e.target.value });
              }}
            />
          </label>
          <label className="sm:col-span-2 text-sm font-medium">
            Dataset
            <select
              required
              className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
              value={form.dataset_key}
              onChange={(e) => {
                setDirty(true);
                setForm({ ...form, dataset_key: e.target.value, dimensions: [], measures: [] });
              }}
            >
              <option value="">Choose a dataset</option>
              {datasets.map((item) => (
                <option key={item.key} value={item.key}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </CardContent>
      </Card>
      {dataset && (
        <Card>
          <CardHeader>
            <CardTitle>2. Dimensions and measures</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-6 md:grid-cols-2">
            <fieldset>
              <legend className="mb-2 font-medium">Dimensions</legend>
              <div className="space-y-2">
                {dataset.dimensions.map((item) => (
                  <label key={item.key} className="flex items-start gap-2 rounded border p-2">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={form.dimensions.includes(item.key)}
                      onChange={() => toggle("dimensions", item.key)}
                    />
                    <span>
                      <span className="block text-sm font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {item.type} · {item.sensitivity}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="mb-2 font-medium">Measures</legend>
              <div className="space-y-2">
                {dataset.measures.map((item) => (
                  <label key={item.key} className="flex items-start gap-2 rounded border p-2">
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={form.measures.some((x) => x.key === item.key)}
                      onChange={() => toggle("measures", item.key)}
                    />
                    <span>
                      <span className="block text-sm font-medium">{item.label}</span>
                      <span className="text-xs text-muted-foreground">
                        {item.aggregation} · {item.result_type}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>3. Limits and validation preview</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">
            Row limit
            <Input
              type="number"
              min={1}
              max={dataset?.maximum_row_limit ?? 10000}
              value={form.row_limit ?? 500}
              onChange={(e) => {
                setDirty(true);
                setForm({ ...form, row_limit: Number(e.target.value) });
              }}
            />
          </label>
          <label className="text-sm font-medium">
            Cache lifetime (seconds)
            <Input
              type="number"
              min={0}
              max={86400}
              value={form.cache_ttl_seconds ?? 300}
              onChange={(e) => {
                setDirty(true);
                setForm({ ...form, cache_ttl_seconds: Number(e.target.value) });
              }}
            />
          </label>
          <div className="sm:col-span-2 flex items-center gap-2 rounded-md bg-muted p-3 text-sm">
            <CheckCircle2 className="h-5 w-5 text-primary" />
            <span>
              {valid
                ? "Ready for server schema validation."
                : "Choose a dataset and at least one dimension or measure."}
            </span>
          </div>
        </CardContent>
      </Card>
      <div className="flex justify-end">
        <Button type="submit" disabled={!valid || pending}>
          {pending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
