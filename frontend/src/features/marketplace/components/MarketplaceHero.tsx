import { ArrowRight, Store, WifiOff } from "lucide-react";
import { Link } from "react-router-dom";
import { ENDPOINTS, type MarketplaceCapability, type MarketplaceDeployment } from "../contracts";

interface MarketplaceHeroProps {
  capabilities: readonly MarketplaceCapability[];
  deployment: MarketplaceDeployment;
}

export function MarketplaceHero({ capabilities, deployment }: MarketplaceHeroProps) {
  const isolated =
    deployment.applicationMode === "self-hosted" && deployment.licenseMode === "isolated";

  return (
    <>
      <header className="relative overflow-hidden rounded-2xl border bg-gradient-to-br from-primary/10 via-card to-amber-500/5 px-6 py-8 sm:px-8 lg:px-10 lg:py-10">
        <div className="relative z-10 max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-primary">
            Capability marketplace
          </p>
          <h1 className="mt-3 text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Start open. Expand for your industry.
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
            Explore everything available to your tenant, including premium capabilities you have not
            licensed yet. Locked modules stay visible so your team can compare fit before buying.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Link
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              to={ENDPOINTS.MARKETPLACE.COMPARE}
            >
              Compare capabilities
              <ArrowRight aria-hidden="true" className="ml-2 h-4 w-4" />
            </Link>
            <span className="text-sm text-muted-foreground">
              {capabilities.filter((item) => item.commercialModel === "free").length} included ·{" "}
              {capabilities.filter((item) => item.commercialModel === "paid").length} industry
              modules
            </span>
          </div>
        </div>
        <Store
          aria-hidden="true"
          className="absolute -bottom-8 -right-8 h-52 w-52 text-primary/5"
        />
      </header>

      {isolated && (
        <section
          aria-label="Isolated deployment information"
          className="flex items-start gap-3 rounded-xl border border-sky-500/25 bg-sky-500/5 p-5"
        >
          <WifiOff
            aria-hidden="true"
            className="mt-0.5 h-5 w-5 shrink-0 text-sky-700 dark:text-sky-300"
          />
          <div>
            <h2 className="font-semibold">Offline purchase and trials are supported</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Browse and compare the full catalog without an internet connection. Open any locked
              capability to generate a portable trial request and follow the signed-entitlement
              hand-off.
            </p>
          </div>
        </section>
      )}
    </>
  );
}
