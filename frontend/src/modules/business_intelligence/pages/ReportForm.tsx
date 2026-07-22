import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui";
import type { QueryListItem, ReportCreate, ReportType } from "../contracts";
import { MutationError, UnsavedWarning } from "./shared";
// eslint-disable-next-line max-lines-per-function -- cohesive accessible report authoring workflow
export function ReportForm({
  initial,
  queries,
  onSubmit,
  pending,
  error,
  submitLabel,
  storageKey,
}: {
  initial: ReportCreate;
  queries: QueryListItem[];
  onSubmit: (value: ReportCreate) => void;
  pending: boolean;
  error: unknown;
  submitLabel: string;
  storageKey: string;
}) {
  const [form, setForm] = useState<ReportCreate>(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      return saved ? (JSON.parse(saved) as ReportCreate) : initial;
    } catch {
      return initial;
    }
  });
  const [dirty, setDirty] = useState(false);
  const update = (next: ReportCreate) => {
    setDirty(true);
    setForm(next);
    localStorage.setItem(storageKey, JSON.stringify(next));
  };
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
          <CardTitle>Report definition</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <label className="text-sm font-medium">
            Code
            <Input
              required
              maxLength={64}
              value={form.report_code}
              onChange={(e) =>
                update({
                  ...form,
                  report_code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/gu, ""),
                })
              }
            />
          </label>
          <label className="text-sm font-medium">
            Name
            <Input
              required
              value={form.report_name}
              onChange={(e) => update({ ...form, report_name: e.target.value })}
            />
          </label>
          <label className="sm:col-span-2 text-sm font-medium">
            Description
            <Textarea
              value={form.description ?? ""}
              onChange={(e) => update({ ...form, description: e.target.value })}
            />
          </label>
          <label className="text-sm font-medium">
            Published query
            <select
              required
              className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
              value={form.query_definition_id}
              onChange={(e) => update({ ...form, query_definition_id: e.target.value })}
            >
              <option value="">Choose a query</option>
              {queries.map((query) => (
                <option key={query.id} value={query.id}>
                  {query.name} · {query.dataset_key}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium">
            Report type
            <select
              className="mt-1 h-10 w-full rounded-md border border-input bg-background px-3"
              value={form.report_type}
              onChange={(e) => update({ ...form, report_type: e.target.value as ReportType })}
            >
              <option value="table">Table</option>
              <option value="pivot">Pivot</option>
              <option value="chart">Chart</option>
              <option value="kpi">KPI</option>
            </select>
          </label>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Visualization</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Columns and formatting derive from the governed query result. Visualization
            compatibility is validated by the server before publication.
          </p>
        </CardContent>
      </Card>
      <div className="flex justify-end">
        <Button
          disabled={pending || !form.report_code || !form.report_name || !form.query_definition_id}
        >
          {pending ? "Saving…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
