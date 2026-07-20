/**
 * Public frontend contract for the SARAISE capability marketplace.
 *
 * Paid modules integrate with this surface by contributing a catalog entry and
 * a stable entitlement key. UI code must evaluate the entitlement key; it must
 * never remove a paid capability merely because the current tenant cannot run it.
 */

export type MarketplaceDeploymentMode = "development" | "saas" | "self-hosted";
export type MarketplaceLicenseMode = "connected" | "isolated";
export type CapabilityCommercialModel = "free" | "paid";
export type CapabilityAccess = "included" | "entitled" | "trial" | "locked";

export interface MarketplaceDeployment {
  applicationMode: MarketplaceDeploymentMode;
  licenseMode: MarketplaceLicenseMode;
}

export interface CapabilityFeature {
  id: string;
  label: string;
  description: string;
}

/** Catalog metadata supplied by OSS or a paid extension package. */
export interface CapabilityDefinition {
  id: string;
  name: string;
  summary: string;
  description: string;
  category: string;
  commercialModel: CapabilityCommercialModel;
  entitlementKey?: string;
  industries: readonly string[];
  outcomes: readonly string[];
  features: readonly CapabilityFeature[];
  trialAvailable: boolean;
  launchPath?: string;
}

/** Tenant-aware view of a catalog definition. */
export interface MarketplaceCapability extends CapabilityDefinition {
  access: CapabilityAccess;
}

export interface MarketplaceEntitlements {
  active: ReadonlySet<string>;
  trials: ReadonlySet<string>;
}

export interface OfflineTrialRequest {
  schemaVersion: "1.0";
  requestType: "offline-trial";
  capabilityId: string;
  entitlementKey: string;
  generatedAt: string;
}

/**
 * Frontend routes and local hand-off destinations.
 *
 * There is deliberately no mandatory online marketplace API: isolated
 * self-hosted installations must be able to discover and evaluate modules.
 */
export const ENDPOINTS = {
  MARKETPLACE: {
    LIST: "/marketplace",
    COMPARE: "/marketplace/compare",
    DETAIL_PATTERN: "/marketplace/:capabilityId",
    DETAIL: (capabilityId: string) => `/marketplace/${encodeURIComponent(capabilityId)}` as const,
    OFFLINE_TRIAL: (capabilityId: string) =>
      `/marketplace/${encodeURIComponent(capabilityId)}#offline-trial` as const,
  },
  SUPPORT: {
    TRIAL: (capabilityId: string) =>
      `/support?topic=trial&capability=${encodeURIComponent(capabilityId)}` as const,
    UPGRADE: (capabilityId: string) =>
      `/support?topic=upgrade&capability=${encodeURIComponent(capabilityId)}` as const,
  },
  CAPABILITIES: {
    WORKFLOW_AUTOMATION: "/workflow-automation/workflows",
    DOCUMENT_MANAGEMENT: "/dms",
  },
} as const;
