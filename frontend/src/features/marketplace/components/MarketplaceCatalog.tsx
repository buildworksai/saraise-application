import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { EmptyState } from "@/components/ui/EmptyState";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/utils";
import type { MarketplaceCapability, MarketplaceDeployment } from "../contracts";
import { CapabilityCard } from "./CapabilityCard";

interface MarketplaceCatalogProps {
  capabilities: readonly MarketplaceCapability[];
  deployment: MarketplaceDeployment;
}

export function MarketplaceCatalog({ capabilities, deployment }: MarketplaceCatalogProps) {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("All");
  const categories = useMemo(
    () => ["All", ...Array.from(new Set(capabilities.map((item) => item.category)))],
    [capabilities]
  );
  const filteredCapabilities = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return capabilities.filter((capability) => {
      const matchesCategory = category === "All" || capability.category === category;
      const searchable = [
        capability.name,
        capability.summary,
        capability.category,
        ...capability.industries,
        ...capability.outcomes,
      ]
        .join(" ")
        .toLocaleLowerCase();
      return matchesCategory && (!normalizedQuery || searchable.includes(normalizedQuery));
    });
  }, [capabilities, category, query]);

  return (
    <section aria-labelledby="catalog-heading" className="space-y-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-sm font-semibold text-primary">Discover</p>
          <h2 className="mt-1 text-2xl font-bold" id="catalog-heading">
            All capabilities
          </h2>
        </div>
        <div className="relative w-full lg:max-w-sm">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            aria-label="Search capabilities"
            className="pl-10"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search capabilities or outcomes"
            type="search"
            value={query}
          />
        </div>
      </div>

      <div
        aria-label="Filter capabilities by category"
        className="flex gap-2 overflow-x-auto pb-1"
        role="group"
      >
        {categories.map((item) => (
          <button
            aria-pressed={category === item}
            className={cn(
              "whitespace-nowrap rounded-full border px-4 py-2 text-sm font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              category === item
                ? "border-primary bg-primary text-primary-foreground"
                : "bg-card hover:bg-muted"
            )}
            key={item}
            onClick={() => setCategory(item)}
            type="button"
          >
            {item}
          </button>
        ))}
      </div>

      {filteredCapabilities.length === 0 ? (
        <EmptyState
          action={{
            label: "Clear filters",
            onClick: () => {
              setCategory("All");
              setQuery("");
            },
          }}
          description="Try another category or search term. No capability was hidden because of entitlement status."
          icon={Search}
          title="No matching capabilities"
        />
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {filteredCapabilities.map((capability) => (
            <CapabilityCard capability={capability} deployment={deployment} key={capability.id} />
          ))}
        </div>
      )}
    </section>
  );
}
