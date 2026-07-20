import { ArrowLeft, Check, Layers3, LockKeyhole } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  BUILT_IN_CAPABILITIES,
  EMPTY_ENTITLEMENTS,
  getMarketplaceDeployment,
  resolveCapabilities,
} from "../catalog";
import { TrialEntry } from "../components/TrialEntry";
import { UpgradePrompt } from "../components/UpgradePrompt";
import {
  ENDPOINTS,
  type CapabilityDefinition,
  type MarketplaceCapability,
  type MarketplaceDeployment,
  type MarketplaceEntitlements,
} from "../contracts";

interface CapabilityDetailPageProps {
  capabilityId?: string;
  definitions?: readonly CapabilityDefinition[];
  entitlements?: MarketplaceEntitlements;
  deployment?: MarketplaceDeployment;
}

function CapabilityBenefits({ capability }: { capability: MarketplaceCapability }) {
  return (
    <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
      <section
        aria-labelledby="capabilities-heading"
        className="rounded-xl border bg-card p-6 sm:p-8"
      >
        <h2 className="text-xl font-semibold" id="capabilities-heading">
          What your team gets
        </h2>
        <div className="mt-5 space-y-5">
          {capability.features.map((feature) => (
            <div className="flex gap-3" key={feature.id}>
              <span className="mt-0.5 rounded-full bg-primary/10 p-1 text-primary">
                <Check aria-hidden="true" className="h-4 w-4" />
              </span>
              <div>
                <h3 className="font-semibold">{feature.label}</h3>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {feature.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </section>
      <section aria-labelledby="outcomes-heading" className="rounded-xl border bg-card p-6 sm:p-8">
        <h2 className="text-xl font-semibold" id="outcomes-heading">
          Expected operational outcomes
        </h2>
        <ul className="mt-5 space-y-3">
          {capability.outcomes.map((outcome) => (
            <li className="flex gap-2 text-sm" key={outcome}>
              <Check aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              {outcome}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function CapabilityDetailPage({
  capabilityId,
  definitions = BUILT_IN_CAPABILITIES,
  entitlements = EMPTY_ENTITLEMENTS,
  deployment = getMarketplaceDeployment(),
}: CapabilityDetailPageProps) {
  const navigate = useNavigate();
  const params = useParams<{ capabilityId: string }>();
  const resolvedId = capabilityId ?? params.capabilityId;
  const capability = resolveCapabilities(definitions, entitlements).find(
    (item) => item.id === resolvedId
  );

  if (!capability) {
    return (
      <EmptyState
        action={{
          label: "Return to marketplace",
          onClick: () => navigate(ENDPOINTS.MARKETPLACE.LIST),
        }}
        description="This capability is not present in the installed catalog. Verify its ID or extension package."
        icon={Layers3}
        title="Capability not found"
      />
    );
  }

  const locked = capability.access === "locked";

  return (
    <div className="mx-auto w-full max-w-6xl space-y-7 pb-10">
      <Link
        className="inline-flex items-center text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        to={ENDPOINTS.MARKETPLACE.LIST}
      >
        <ArrowLeft aria-hidden="true" className="mr-2 h-4 w-4" />
        Back to marketplace
      </Link>

      <header className="relative overflow-hidden rounded-2xl border bg-card p-6 sm:p-8 lg:p-10">
        <div className="max-w-3xl">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-semibold">
              {capability.category}
            </span>
            <span className="rounded-full bg-muted px-3 py-1 text-xs font-semibold capitalize">
              {capability.commercialModel}
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-xs font-semibold">
              {locked ? (
                <LockKeyhole aria-hidden="true" className="h-3.5 w-3.5" />
              ) : (
                <Check aria-hidden="true" className="h-3.5 w-3.5" />
              )}
              {locked ? "Locked" : capability.access === "trial" ? "Trial active" : "Available"}
            </span>
          </div>
          <h1 className="mt-5 text-3xl font-bold tracking-tight sm:text-4xl">{capability.name}</h1>
          <p className="mt-4 text-lg leading-8 text-muted-foreground">{capability.description}</p>
          <p className="mt-5 text-sm text-muted-foreground">
            For {capability.industries.join(" · ")}
          </p>
        </div>
      </header>

      <CapabilityBenefits capability={capability} />

      {locked && <UpgradePrompt capability={capability} deployment={deployment} />}
      <TrialEntry capability={capability} deployment={deployment} />
    </div>
  );
}
