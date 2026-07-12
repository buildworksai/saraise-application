import { AlertTriangle } from "lucide-react";

interface ModuleUnavailablePageProps {
  moduleName: string;
}

export function ModuleUnavailablePage({ moduleName }: ModuleUnavailablePageProps) {
  return (
    <section className="mx-auto max-w-2xl rounded-lg border border-amber-500/40 bg-amber-500/5 p-8">
      <div className="flex items-start gap-4">
        <AlertTriangle className="mt-1 size-6 shrink-0 text-amber-600" aria-hidden="true" />
        <div>
          <h1 className="text-2xl font-semibold">{moduleName} is not available</h1>
          <p className="mt-2 text-muted-foreground">
            This module has no published, verified API contract in this release. No request was
            sent to an unverified endpoint.
          </p>
        </div>
      </div>
    </section>
  );
}
