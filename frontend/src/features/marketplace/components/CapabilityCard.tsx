import { ArrowRight, Check, LockKeyhole, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/Card";
import { cn } from "@/lib/utils";
import { ENDPOINTS, type MarketplaceCapability, type MarketplaceDeployment } from "../contracts";
import { UpgradePrompt } from "./UpgradePrompt";

interface CapabilityCardProps {
  capability: MarketplaceCapability;
  deployment: MarketplaceDeployment;
}

const ACCESS_LABELS = {
  included: "Included",
  entitled: "Licensed",
  trial: "Trial active",
  locked: "Paid · Locked",
} as const;

export function CapabilityCard({ capability, deployment }: CapabilityCardProps) {
  const locked = capability.access === "locked";

  return (
    <Card
      className={cn(
        "group flex h-full flex-col overflow-hidden transition duration-200 hover:-translate-y-0.5 hover:shadow-lg",
        locked && "border-amber-500/25"
      )}
      data-access={capability.access}
    >
      <CardHeader className="space-y-4">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
            {capability.category}
          </span>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold",
              locked
                ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
            )}
          >
            {locked ? (
              <LockKeyhole aria-hidden="true" className="h-3.5 w-3.5" />
            ) : (
              <Check aria-hidden="true" className="h-3.5 w-3.5" />
            )}
            {ACCESS_LABELS[capability.access]}
          </span>
        </div>
        <div>
          <CardTitle className="text-xl leading-tight">{capability.name}</CardTitle>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{capability.summary}</p>
        </div>
      </CardHeader>
      <CardContent className="flex-1">
        <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Built for
        </p>
        <ul className="space-y-2 text-sm" aria-label={`${capability.name} outcomes`}>
          {capability.outcomes.slice(0, 3).map((outcome) => (
            <li className="flex gap-2" key={outcome}>
              <Sparkles aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span>{outcome}</span>
            </li>
          ))}
        </ul>
      </CardContent>
      <CardFooter className="block border-t bg-muted/20 pt-5">
        {locked ? (
          <UpgradePrompt capability={capability} deployment={deployment} compact />
        ) : (
          <Link
            className="inline-flex min-h-10 items-center text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            to={capability.launchPath ?? ENDPOINTS.MARKETPLACE.DETAIL(capability.id)}
          >
            {capability.launchPath ? "Open capability" : "View capability"}
            <ArrowRight aria-hidden="true" className="ml-2 h-4 w-4" />
          </Link>
        )}
      </CardFooter>
    </Card>
  );
}
