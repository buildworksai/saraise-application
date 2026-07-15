/**
 * Self-Hosted Licensing Contracts
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * Platform configuration belongs to the Control Plane; only self-hosted
 * license status and activation are permitted here.
 */

export interface LicenseInfo {
  organization_name: string;
  tier: string;
  status: string;
  expires_at: string;
  days_remaining: number;
  is_valid: boolean;
  features: {
    module: string;
    licensed: boolean;
    tier_required: string;
  }[];
}

export interface LicenseActivationRequest {
  license_key: string;
}

export const ENDPOINTS = {
  LICENSING: {
    STATUS: '/api/v1/licensing/status/',
    ACTIVATE: '/api/v1/licensing/activate/',
  },
} as const;
