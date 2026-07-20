import { Download, ExternalLink, FileKey2, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { ENDPOINTS, type MarketplaceCapability, type MarketplaceDeployment } from "../contracts";
import { createOfflineTrialRequest } from "../offline-trial";

interface TrialEntryProps {
  capability: MarketplaceCapability;
  deployment: MarketplaceDeployment;
  now?: () => Date;
}

function downloadRequest(request: ReturnType<typeof createOfflineTrialRequest>): void {
  const blob = new Blob([JSON.stringify(request, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `saraise-${request.capabilityId}-trial-request.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function TrialEntry({ capability, deployment, now }: TrialEntryProps) {
  if (!capability.trialAvailable || capability.access !== "locked") return null;

  const isolated =
    deployment.applicationMode === "self-hosted" && deployment.licenseMode === "isolated";

  if (!isolated) {
    return (
      <section aria-labelledby="trial-heading" className="rounded-xl border bg-primary/5 p-6">
        <div className="flex items-start gap-3">
          <ShieldCheck aria-hidden="true" className="mt-0.5 h-6 w-6 shrink-0 text-primary" />
          <div>
            <h2 className="text-lg font-semibold" id="trial-heading">
              Evaluate with your own workflow
            </h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              Request a guided demo or time-limited tenant trial. A SARAISE specialist will confirm
              fit and activation requirements before anything changes in your environment.
            </p>
            <Link
              className="mt-4 inline-flex items-center justify-center rounded-md bg-primary px-6 py-3 text-base font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              to={ENDPOINTS.SUPPORT.TRIAL(capability.id)}
            >
              Request a trial or demo
              <ExternalLink aria-hidden="true" className="ml-2 h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="offline-trial-heading"
      className="scroll-mt-6 rounded-xl border border-sky-500/25 bg-sky-500/5 p-6"
      id="offline-trial"
    >
      <div className="flex items-start gap-3">
        <FileKey2
          aria-hidden="true"
          className="mt-0.5 h-6 w-6 shrink-0 text-sky-700 dark:text-sky-300"
        />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-sky-700 dark:text-sky-300">
            Self-hosted · isolated licensing
          </p>
          <h2 className="mt-1 text-lg font-semibold" id="offline-trial-heading">
            Start an offline evaluation
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            No connection to the SARAISE platform is required. Generate a non-secret request file,
            move it through your approved transfer process, and return the signed trial entitlement
            to your SARAISE administrator.
          </p>
          <ol className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
            <li className="rounded-lg bg-background/70 p-3">
              <strong className="block">1. Generate</strong>Download the portable request.
            </li>
            <li className="rounded-lg bg-background/70 p-3">
              <strong className="block">2. Exchange</strong>Send it from a connected workstation.
            </li>
            <li className="rounded-lg bg-background/70 p-3">
              <strong className="block">3. Apply</strong>Import the signed entitlement offline.
            </li>
          </ol>
          <Button
            className="mt-4"
            onClick={() => downloadRequest(createOfflineTrialRequest(capability, now))}
            size="lg"
          >
            <Download aria-hidden="true" className="mr-2 h-4 w-4" />
            Download offline trial request
          </Button>
          <p className="mt-3 text-xs text-muted-foreground">
            The file contains only the capability ID, entitlement key, schema version, and
            generation time.
          </p>
        </div>
      </div>
    </section>
  );
}
