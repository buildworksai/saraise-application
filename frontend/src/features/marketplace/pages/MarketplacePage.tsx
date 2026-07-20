import { useMemo } from "react";
import { ErrorState } from "@/components/ui/ErrorState";
import {
  BUILT_IN_CAPABILITIES,
  EMPTY_ENTITLEMENTS,
  getMarketplaceDeployment,
  resolveCapabilities,
} from "../catalog";
import { MarketplaceCatalog } from "../components/MarketplaceCatalog";
import { MarketplaceHero } from "../components/MarketplaceHero";
import { MarketplaceSkeleton } from "../components/MarketplaceSkeleton";
import {
  type CapabilityDefinition,
  type MarketplaceDeployment,
  type MarketplaceEntitlements,
} from "../contracts";

export interface MarketplacePageProps {
  definitions?: readonly CapabilityDefinition[];
  entitlements?: MarketplaceEntitlements;
  deployment?: MarketplaceDeployment;
  state?: "loading" | "ready" | "error";
  errorMessage?: string;
  onRetry?: () => void;
}

export function MarketplacePage({
  definitions = BUILT_IN_CAPABILITIES,
  entitlements = EMPTY_ENTITLEMENTS,
  deployment = getMarketplaceDeployment(),
  state = "ready",
  errorMessage = "The capability catalog is unavailable. Verify the application package and try again.",
  onRetry,
}: MarketplacePageProps) {
  const capabilities = useMemo(
    () => resolveCapabilities(definitions, entitlements),
    [definitions, entitlements]
  );
  if (state === "loading") return <MarketplaceSkeleton />;
  if (state === "error") {
    return <ErrorState title="Marketplace unavailable" message={errorMessage} onRetry={onRetry} />;
  }

  return (
    <div className="mx-auto w-full max-w-7xl space-y-8 pb-10">
      <MarketplaceHero capabilities={capabilities} deployment={deployment} />
      <MarketplaceCatalog capabilities={capabilities} deployment={deployment} />
    </div>
  );
}
