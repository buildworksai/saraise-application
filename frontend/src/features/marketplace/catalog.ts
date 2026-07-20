import type {
  CapabilityDefinition,
  MarketplaceCapability,
  MarketplaceDeployment,
  MarketplaceEntitlements,
  MarketplaceLicenseMode,
} from "./contracts";
import { ENDPOINTS } from "./contracts";

/**
 * Built-in discovery catalog. Paid packages can append definitions at the app
 * composition boundary without changing the marketplace rendering components.
 */
export const BUILT_IN_CAPABILITIES: readonly CapabilityDefinition[] = [
  {
    id: "workflow-automation",
    name: "Workflow Automation",
    summary: "Design approvals and repeatable business processes without custom code.",
    description:
      "Build, run, and audit tenant-scoped workflows with human approvals, schedules, and operational visibility.",
    category: "Platform",
    commercialModel: "free",
    industries: ["All industries"],
    outcomes: ["Shorter cycle times", "Auditable approvals", "Fewer manual hand-offs"],
    features: [
      {
        id: "workflow-designer",
        label: "Workflow designer",
        description: "Model repeatable flows and approval paths.",
      },
      {
        id: "task-inbox",
        label: "Task inbox",
        description: "Give operators one accountable work queue.",
      },
      {
        id: "execution-history",
        label: "Execution history",
        description: "Trace each run from trigger to outcome.",
      },
    ],
    trialAvailable: false,
    launchPath: ENDPOINTS.CAPABILITIES.WORKFLOW_AUTOMATION,
  },
  {
    id: "document-management",
    name: "Document Management",
    summary: "Organize governed business records with version-aware collaboration.",
    description:
      "Manage tenant documents, metadata, retention context, and controlled access from one operational workspace.",
    category: "Platform",
    commercialModel: "free",
    industries: ["All industries"],
    outcomes: ["One source of truth", "Faster retrieval", "Controlled collaboration"],
    features: [
      {
        id: "governed-library",
        label: "Governed library",
        description: "Keep business records structured and accessible.",
      },
      {
        id: "document-metadata",
        label: "Document metadata",
        description: "Classify content using consistent business context.",
      },
      {
        id: "version-history",
        label: "Version history",
        description: "Maintain a reliable record of change.",
      },
    ],
    trialAvailable: false,
    launchPath: ENDPOINTS.CAPABILITIES.DOCUMENT_MANAGEMENT,
  },
  {
    id: "manufacturing-operations",
    name: "Manufacturing Operations",
    summary: "Connect production, quality, maintenance, and traceability on the shop floor.",
    description:
      "An industry module for production teams that need real-time work-order control, quality gates, and equipment insight.",
    category: "Manufacturing",
    commercialModel: "paid",
    entitlementKey: "industry.manufacturing.operations",
    industries: ["Discrete manufacturing", "Process manufacturing", "Industrial equipment"],
    outcomes: [
      "Higher schedule adherence",
      "Lower quality escape rate",
      "Reduced unplanned downtime",
    ],
    features: [
      {
        id: "production-control",
        label: "Production control",
        description: "Coordinate work orders, operations, and material readiness.",
      },
      {
        id: "quality-gates",
        label: "In-process quality gates",
        description: "Stop defects at the operation where they originate.",
      },
      {
        id: "maintenance-insight",
        label: "Maintenance insight",
        description: "Link equipment condition to production impact.",
      },
    ],
    trialAvailable: true,
  },
  {
    id: "healthcare-operations",
    name: "Healthcare Operations",
    summary: "Coordinate compliant care operations, capacity, and service workflows.",
    description:
      "An industry module for healthcare operators that unifies service coordination and evidence-ready operational controls.",
    category: "Healthcare",
    commercialModel: "paid",
    entitlementKey: "industry.healthcare.operations",
    industries: ["Healthcare providers", "Diagnostics", "Care networks"],
    outcomes: [
      "Faster service coordination",
      "Stronger evidence trails",
      "Improved capacity visibility",
    ],
    features: [
      {
        id: "service-coordination",
        label: "Service coordination",
        description: "Orchestrate accountable, role-aware operational work.",
      },
      {
        id: "capacity-planning",
        label: "Capacity planning",
        description: "Understand constraints before they affect service.",
      },
      {
        id: "compliance-evidence",
        label: "Compliance evidence",
        description: "Preserve evidence throughout the operating workflow.",
      },
    ],
    trialAvailable: true,
  },
  {
    id: "financial-services-operations",
    name: "Financial Services Operations",
    summary: "Control regulated workflows, cases, and operational risk from intake to closure.",
    description:
      "An industry module for financial institutions requiring defensible case handling, controls, and exception management.",
    category: "Financial services",
    commercialModel: "paid",
    entitlementKey: "industry.financial-services.operations",
    industries: ["Banking", "Insurance", "Capital markets"],
    outcomes: ["Lower operational risk", "Faster case resolution", "Consistent controls"],
    features: [
      {
        id: "case-orchestration",
        label: "Regulated case orchestration",
        description: "Keep evidence and accountability attached to every decision.",
      },
      {
        id: "controls-monitoring",
        label: "Controls monitoring",
        description: "Surface exceptions before they become incidents.",
      },
      {
        id: "operational-risk",
        label: "Operational risk views",
        description: "Connect work queues to risk and service impact.",
      },
    ],
    trialAvailable: true,
  },
] as const;

export const EMPTY_ENTITLEMENTS: MarketplaceEntitlements = {
  active: new Set<string>(),
  trials: new Set<string>(),
};

/** Resolve catalog metadata against the current tenant's effective entitlements. */
export function resolveCapabilities(
  definitions: readonly CapabilityDefinition[],
  entitlements: MarketplaceEntitlements
): readonly MarketplaceCapability[] {
  return definitions.map((definition) => {
    if (definition.commercialModel === "free") {
      return { ...definition, access: "included" };
    }

    const entitlementKey = definition.entitlementKey;
    if (!entitlementKey) {
      throw new Error(`Paid capability ${definition.id} is missing an entitlement key.`);
    }

    const access = entitlements.active.has(entitlementKey)
      ? "entitled"
      : entitlements.trials.has(entitlementKey)
        ? "trial"
        : "locked";
    return { ...definition, access };
  });
}

function getLicenseMode(value: unknown): MarketplaceLicenseMode {
  return value === "isolated" ? "isolated" : "connected";
}

/** Read deployment facts only; this function does not infer entitlements. */
export function getMarketplaceDeployment(): MarketplaceDeployment {
  const rawMode = import.meta.env.VITE_SARAISE_MODE;
  const applicationMode = rawMode === "saas" || rawMode === "self-hosted" ? rawMode : "development";

  return {
    applicationMode,
    licenseMode: getLicenseMode(import.meta.env.VITE_SARAISE_LICENSE_MODE),
  };
}
