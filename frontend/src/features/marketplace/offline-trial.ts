import type { MarketplaceCapability, OfflineTrialRequest } from "./contracts";

/** Build the transparent, non-secret request exchanged by isolated installations. */
export function createOfflineTrialRequest(
  capability: MarketplaceCapability,
  now: () => Date = () => new Date()
): OfflineTrialRequest {
  if (capability.commercialModel !== "paid" || !capability.entitlementKey) {
    throw new Error(`Capability ${capability.id} does not support an offline paid-module trial.`);
  }

  return {
    schemaVersion: "1.0",
    requestType: "offline-trial",
    capabilityId: capability.id,
    entitlementKey: capability.entitlementKey,
    generatedAt: now().toISOString(),
  };
}
