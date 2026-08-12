import { useEffect, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, ChevronLeft, ChevronRight, Inbox, Loader2 } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui";
import { Label } from "@/components/ui/Label";
import type { CollectionResult } from "../services/bank-reconciliation-service";

export function Page({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    document.title = `${title} · SARAISE`;
  }, [title]);
  return (
    <main className="mx-auto w-full max-w-[1600px] space-y-6 p-4 sm:p-6 lg:p-8">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">{title}</h1>
          {description && (
            <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>
          )}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </header>
      {children}
    </main>
  );
}

export function LoadingPage({ title }: { title: string }) {
  return (
    <Page title={title}>
      <Card aria-busy="true" aria-label={`Loading ${title}`}>
        <CardContent className="pt-6">
          <TableSkeleton rows={6} columns={5} />
        </CardContent>
      </Card>
    </Page>
  );
}

export function ErrorPage({
  title,
  error,
  retry,
}: {
  title: string;
  error: Error;
  retry: () => void;
}) {
  const apiError = error instanceof ApiError ? error : undefined;
  if (apiError?.status === 403)
    return (
      <Page title={title}>
        <Card>
          <CardContent className="flex gap-3 pt-6">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <h2 className="font-semibold">Permission required</h2>
              <p className="text-sm text-muted-foreground">
                Your access policy does not allow this action.
              </p>
              {apiError.correlationId && (
                <p className="mt-2 font-mono text-xs">Correlation ID: {apiError.correlationId}</p>
              )}
            </div>
          </CardContent>
        </Card>
      </Page>
    );
  return (
    <Page title={title}>
      <ErrorState
        message={`${apiError?.message ?? "This information could not be loaded."}${apiError?.correlationId ? ` Correlation ID: ${apiError.correlationId}` : ""}`}
        onRetry={retry}
      />
    </Page>
  );
}

export function EmptyPanel({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <EmptyState icon={Inbox} title={title} description={description} action={action} />
      </CardContent>
    </Card>
  );
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormCard({
  title,
  onSubmit,
  pending,
  submitLabel,
  children,
}: {
  title: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pending: boolean;
  submitLabel: string;
  children: ReactNode;
}) {
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={onSubmit} noValidate>
          {children}
          <Button disabled={pending} type="submit">
            {pending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {pending ? "Saving…" : submitLabel}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

export function TableShell({ children }: { children: ReactNode }) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">{children}</table>
      </div>
    </Card>
  );
}
export function Th({ children }: { children: ReactNode }) {
  return (
    <th
      scope="col"
      className="bg-muted/60 px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground"
    >
      {children}
    </th>
  );
}
export function Td({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <td className={`border-t px-4 py-3 align-top ${className}`}>{children}</td>;
}

export function Pager<T>({
  result,
  page,
  onPage,
}: {
  result: CollectionResult<T>;
  page: number;
  onPage: (page: number) => void;
}) {
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between text-sm">
      <span>
        {result.pagination.count} results · Page {result.pagination.page} of{" "}
        {Math.max(1, result.pagination.total_pages)}
      </span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!result.pagination.has_previous}
          onClick={() => onPage(Math.max(1, page - 1))}
        >
          <ChevronLeft className="h-4 w-4" />
          Previous
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!result.pagination.has_next}
          onClick={() => onPage(page + 1)}
        >
          Next
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}

export function StatusPill({ value }: { value: string }) {
  return (
    <span className="inline-flex rounded-full border bg-muted/40 px-2 py-0.5 text-xs font-medium capitalize">
      {value.replaceAll("_", " ")}
    </span>
  );
}
export function Money({ value, currency }: { value: string; currency?: string }) {
  return (
    <span className="tabular-nums">
      {currency ? `${currency} ` : ""}
      {value}
    </span>
  );
}
export function DetailGrid({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map(({ label, value }) => (
        <div className="rounded-lg border p-4" key={label}>
          <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {label}
          </dt>
          <dd className="mt-1 text-base font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
export function BackLink({ to, children }: { to: string; children: ReactNode }) {
  const navigate = useNavigate();
  return (
    <Button variant="ghost" onClick={() => navigate(to)}>
      <ChevronLeft className="mr-1 h-4 w-4" />
      {children}
    </Button>
  );
}
