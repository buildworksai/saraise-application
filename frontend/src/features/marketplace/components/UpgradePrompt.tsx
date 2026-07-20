import { ArrowRight, LockKeyhole, RadioTower } from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/utils";
import { ENDPOINTS, type MarketplaceCapability, type MarketplaceDeployment } from "../contracts";

interface UpgradePromptProps {
  capability: MarketplaceCapability;
  deployment: MarketplaceDeployment;
  compact?: boolean;
  className?: string;
}

/** A transparent hand-off for a known locked capability; it never claims activation succeeded. */
export function UpgradePrompt({
  capability,
  deployment,
  compact = false,
  className,
}: UpgradePromptProps) {
  if (capability.access !== "locked") return null;

  const isIsolated =
    deployment.applicationMode === "self-hosted" && deployment.licenseMode === "isolated";
  const destination = compact
    ? ENDPOINTS.MARKETPLACE.DETAIL(capability.id)
    : isIsolated
      ? ENDPOINTS.MARKETPLACE.OFFLINE_TRIAL(capability.id)
      : ENDPOINTS.SUPPORT.UPGRADE(capability.id);

  return (
    <aside
      aria-label={`Upgrade ${capability.name}`}
      className={cn(
        "rounded-xl border border-amber-500/25 bg-amber-500/5",
        compact ? "p-4" : "p-6 sm:p-7",
        className
      )}
    >
      <div className="flex items-start gap-3">
        <span className="rounded-lg bg-amber-500/15 p-2 text-amber-700 dark:text-amber-300">
          {isIsolated ? (
            <RadioTower aria-hidden="true" className="h-5 w-5" />
          ) : (
            <LockKeyhole aria-hidden="true" className="h-5 w-5" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className={cn("font-semibold", compact ? "text-sm" : "text-lg")}>
            Upgrade to unlock
          </h3>
          <p className={cn("mt-1 text-muted-foreground", compact ? "text-xs" : "text-sm")}>
            {isIsolated
              ? "This installation stays offline. Generate a portable request and apply the signed entitlement through your normal administrator hand-off."
              : `Your tenant can discover ${capability.name}, but an active entitlement is required to run it.`}
          </p>
          <Link
            className={cn(
              "mt-4 inline-flex items-center justify-center rounded-md bg-primary font-medium text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              compact ? "px-3 py-1.5 text-sm" : "px-4 py-2 text-sm"
            )}
            to={destination}
          >
            {compact
              ? isIsolated
                ? "View offline options"
                : "Compare and upgrade"
              : isIsolated
                ? "Go to offline options"
                : "Talk to an upgrade specialist"}
            <ArrowRight aria-hidden="true" className="ml-2 h-4 w-4" />
          </Link>
        </div>
      </div>
    </aside>
  );
}
