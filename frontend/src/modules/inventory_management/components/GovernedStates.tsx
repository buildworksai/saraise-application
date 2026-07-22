import { AlertTriangle, LockKeyhole, PackageOpen, RefreshCw } from "lucide-react";
import { ApiError } from "@/services/api-client";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";

export function InventorySkeleton({ label = "Loading inventory" }: { label?: string }) {
  return <div className="space-y-4 p-4 sm:p-8" role="status" aria-label={label}><Skeleton className="h-9 w-64" /><Skeleton className="h-12 w-full" /><Skeleton className="h-72 w-full" /><span className="sr-only">{label}</span></div>;
}

export function InventoryEmpty({ title, detail, action }: { title: string; detail: string; action?: { label: string; onClick: () => void } }) {
  return <Card className="flex min-h-64 flex-col items-center justify-center gap-3 p-8 text-center"><PackageOpen className="h-10 w-10 text-muted-foreground" aria-hidden="true" /><h2 className="text-xl font-semibold">{title}</h2><p className="max-w-xl text-sm text-muted-foreground">{detail}</p>{action ? <Button onClick={action.onClick}>{action.label}</Button> : null}</Card>;
}

export function InventoryErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const apiError = error instanceof ApiError ? error : undefined;
  const denied = apiError?.status === 403;
  const missing = apiError?.status === 404;
  const retryable = apiError ? apiError.status === 429 || apiError.status >= 500 : false;
  const title = denied ? "Access denied" : missing ? "Inventory record unavailable" : "Inventory could not be loaded";
  const detail = denied ? "Your account does not have the required inventory permission. Access is denied by default; ask an administrator to review your role." : missing ? "The record does not exist or is not visible in this tenant." : apiError?.message ?? "An unexpected failure occurred. No data was assumed or fabricated.";
  return <Card className="m-4 border-destructive/40 p-6 sm:m-8" role="alert"><div className="flex gap-3">{denied ? <LockKeyhole className="mt-1 h-5 w-5 text-destructive" /> : <AlertTriangle className="mt-1 h-5 w-5 text-destructive" />}<div className="space-y-2"><h2 className="font-semibold">{title}</h2><p className="text-sm text-muted-foreground">{detail}</p>{apiError?.correlationId ? <p className="font-mono text-xs text-muted-foreground">Correlation ID: {apiError.correlationId}</p> : null}{retryable && onRetry ? <Button variant="outline" onClick={onRetry}><RefreshCw className="mr-2 h-4 w-4" />Retry</Button> : null}</div></div></Card>;
}
