import { ArrowLeft, Scale } from "lucide-react";
import { Link } from "react-router-dom";
import { ErrorState } from "@/components/ui/ErrorState";
import { BUILT_IN_CAPABILITIES, EMPTY_ENTITLEMENTS, resolveCapabilities } from "../catalog";
import { ComparisonView } from "../components/ComparisonView";
import { MarketplaceSkeleton } from "../components/MarketplaceSkeleton";
import { ENDPOINTS, type CapabilityDefinition, type MarketplaceEntitlements } from "../contracts";

interface MarketplaceComparisonPageProps {
  definitions?: readonly CapabilityDefinition[];
  entitlements?: MarketplaceEntitlements;
  state?: "loading" | "ready" | "error";
  onRetry?: () => void;
}

export function MarketplaceComparisonPage({
  definitions = BUILT_IN_CAPABILITIES,
  entitlements = EMPTY_ENTITLEMENTS,
  state = "ready",
  onRetry,
}: MarketplaceComparisonPageProps) {
  if (state === "loading") return <MarketplaceSkeleton />;
  if (state === "error") {
    return (
      <ErrorState
        title="Comparison unavailable"
        message="The capability metadata could not be loaded. No availability assumptions were made."
        onRetry={onRetry}
      />
    );
  }

  const capabilities = resolveCapabilities(definitions, entitlements);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-7 pb-10">
      <Link
        className="inline-flex items-center text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        to={ENDPOINTS.MARKETPLACE.LIST}
      >
        <ArrowLeft aria-hidden="true" className="mr-2 h-4 w-4" />
        Back to marketplace
      </Link>
      <header className="flex flex-col gap-4 rounded-2xl border bg-card p-6 sm:flex-row sm:items-center sm:p-8">
        <span className="w-fit rounded-xl bg-primary/10 p-3 text-primary">
          <Scale aria-hidden="true" className="h-7 w-7" />
        </span>
        <div>
          <p className="text-sm font-semibold text-primary">Side-by-side comparison</p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            Choose capabilities with context
          </h1>
          <p className="mt-2 max-w-3xl text-muted-foreground">
            Compare what is included, what needs an entitlement, whether a trial is available, and
            the operational outcomes each capability targets.
          </p>
        </div>
      </header>
      <ComparisonView capabilities={capabilities} />
    </div>
  );
}
