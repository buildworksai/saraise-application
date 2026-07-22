import type { ReactNode } from 'react';
import { AlertTriangle, ArrowLeft, LockKeyhole, SearchX } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { ErrorState, TableSkeleton } from '@/components/ui';
import { ApiError } from '@/services/api-client';

export function PageScaffold({ title, description, actions, children }: { title: string; description: string; actions?: ReactNode; children: ReactNode }) {
  return <main className="mx-auto w-full max-w-screen-2xl space-y-6 p-4 sm:p-6 lg:p-8">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div><h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{title}</h1><p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p></div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </header>{children}
  </main>;
}

export function BackButton({ to, label = 'Back' }: { to: string; label?: string }) {
  const navigate = useNavigate();
  return <Button variant="ghost" onClick={() => navigate(to)}><ArrowLeft className="mr-2 h-4 w-4" />{label}</Button>;
}

export function LoadingPage({ title = 'Loading records' }: { title?: string }) {
  return <div aria-busy="true" aria-label={title} className="p-4 sm:p-8"><TableSkeleton rows={6} columns={5} /></div>;
}

export function GovernedError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  const apiError = error instanceof ApiError ? error : undefined;
  if (apiError?.status === 403) return <StateCard icon={<LockKeyhole className="h-10 w-10" />} title="Permission required" message="Your current company scope does not allow this operation. Ask an administrator for the required grant." />;
  if (apiError?.status === 404) return <StateCard icon={<SearchX className="h-10 w-10" />} title="Record not found" message="This record does not exist in your tenant, or is no longer available." />;
  const support = apiError?.correlationId ? ` Support reference: ${apiError.correlationId}.` : '';
  return <ErrorState message={`${apiError?.message ?? 'The request could not be completed.'}${support}`} onRetry={onRetry} />;
}

function StateCard({ icon, title, message }: { icon: ReactNode; title: string; message: string }) {
  return <Card><CardContent className="flex min-h-72 flex-col items-center justify-center p-8 text-center"><div className="mb-4 text-muted-foreground">{icon}</div><h2 className="text-xl font-semibold">{title}</h2><p className="mt-2 max-w-lg text-muted-foreground">{message}</p></CardContent></Card>;
}

export function InlineWarning({ children }: { children: ReactNode }) {
  return <div role="status" className="flex gap-3 rounded-lg border border-border bg-muted/50 p-4 text-sm"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" /><div>{children}</div></div>;
}

export function StatusPill({ value }: { value: string }) {
  return <span className="inline-flex rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-medium capitalize text-foreground">{value.replaceAll('_', ' ')}</span>;
}
