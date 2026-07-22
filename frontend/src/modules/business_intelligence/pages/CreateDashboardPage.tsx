import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input, Textarea } from "@/components/ui";
import type { DashboardCreate } from "../contracts";
import { biService, createIdempotencyKey } from "../services/bi-service";
import { BI_PATH, MutationError, PageShell, UnsavedWarning, useDocumentTitle } from "./shared";
const STORAGE_KEY = "bi-dashboard-new";
const EMPTY_DASHBOARD: DashboardCreate = {
  dashboard_code: "",
  dashboard_name: "",
  description: "",
  global_filters: [],
  refresh_interval_seconds: null,
};

const restoreDraft = (): DashboardCreate => {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return saved
      ? ({ ...EMPTY_DASHBOARD, ...JSON.parse(saved) } as DashboardCreate)
      : EMPTY_DASHBOARD;
  } catch {
    return EMPTY_DASHBOARD;
  }
};

export function CreateDashboardPage() {
  useDocumentTitle("Create dashboard");
  const navigate = useNavigate();
  const [form, setForm] = useState<DashboardCreate>(restoreDraft);
  const [dirty, setDirty] = useState(false);
  const mutation = useMutation({
    mutationFn: () => biService.createDashboard(form, createIdempotencyKey()),
    onSuccess: (value) => {
      localStorage.removeItem(STORAGE_KEY);
      navigate(`${BI_PATH}/dashboards/${value.id}/edit`);
    },
  });
  const update = (value: DashboardCreate) => {
    setDirty(true);
    setForm(value);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
  };
  return (
    <PageShell
      title="Create dashboard"
      description="Start with metadata, then configure widgets and sharing in the builder."
    >
      <form
        className="max-w-3xl space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <UnsavedWarning when={dirty && !mutation.isPending} />
        <MutationError error={mutation.error} />
        <Card>
          <CardHeader>
            <CardTitle>Dashboard metadata</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Code
              <Input
                required
                value={form.dashboard_code}
                onChange={(e) =>
                  update({
                    ...form,
                    dashboard_code: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/gu, ""),
                  })
                }
              />
            </label>
            <label className="text-sm font-medium">
              Name
              <Input
                required
                value={form.dashboard_name}
                onChange={(e) => update({ ...form, dashboard_name: e.target.value })}
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
              Automatic refresh (seconds)
              <Input
                type="number"
                min={30}
                max={86400}
                placeholder="Off"
                value={form.refresh_interval_seconds ?? ""}
                onChange={(e) =>
                  update({
                    ...form,
                    refresh_interval_seconds: e.target.value ? Number(e.target.value) : null,
                  })
                }
              />
            </label>
          </CardContent>
        </Card>
        <Button disabled={mutation.isPending || !form.dashboard_code || !form.dashboard_name}>
          {mutation.isPending ? "Creating…" : "Continue to dashboard builder"}
        </Button>
      </form>
    </PageShell>
  );
}
