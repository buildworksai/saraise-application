import { Check, LockKeyhole, Minus } from "lucide-react";
import { Link } from "react-router-dom";
import { ENDPOINTS, type MarketplaceCapability } from "../contracts";

interface ComparisonViewProps {
  capabilities: readonly MarketplaceCapability[];
}

export function ComparisonView({ capabilities }: ComparisonViewProps) {
  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left text-sm">
          <caption className="sr-only">
            Compare included and paid SARAISE capabilities, access, trials, and outcomes.
          </caption>
          <thead className="bg-muted/60">
            <tr>
              <th className="p-4 font-semibold" scope="col">
                Capability
              </th>
              <th className="p-4 font-semibold" scope="col">
                Plan
              </th>
              <th className="p-4 font-semibold" scope="col">
                Access
              </th>
              <th className="p-4 font-semibold" scope="col">
                Trial
              </th>
              <th className="p-4 font-semibold" scope="col">
                Key outcomes
              </th>
              <th className="p-4 font-semibold" scope="col">
                <span className="sr-only">Details</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {capabilities.map((capability) => {
              const locked = capability.access === "locked";
              return (
                <tr className="border-t align-top hover:bg-muted/30" key={capability.id}>
                  <th className="p-4 font-semibold" scope="row">
                    <span className="block">{capability.name}</span>
                    <span className="mt-1 block text-xs font-normal text-muted-foreground">
                      {capability.category}
                    </span>
                  </th>
                  <td className="p-4 capitalize">{capability.commercialModel}</td>
                  <td className="p-4">
                    <span className="inline-flex items-center gap-1.5">
                      {locked ? (
                        <LockKeyhole aria-hidden="true" className="h-4 w-4 text-amber-600" />
                      ) : (
                        <Check aria-hidden="true" className="h-4 w-4 text-emerald-600" />
                      )}
                      {locked
                        ? "Upgrade required"
                        : capability.access === "trial"
                          ? "Trial active"
                          : "Available"}
                    </span>
                  </td>
                  <td className="p-4">
                    {capability.trialAvailable ? (
                      <Check aria-label="Available" className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <Minus
                        aria-label="Not applicable"
                        className="h-4 w-4 text-muted-foreground"
                      />
                    )}
                  </td>
                  <td className="max-w-sm p-4 text-muted-foreground">
                    {capability.outcomes.join(" · ")}
                  </td>
                  <td className="p-4 text-right">
                    <Link
                      className="font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      to={ENDPOINTS.MARKETPLACE.DETAIL(capability.id)}
                    >
                      Compare details
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
