/**
 * Email Marketing Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Email Marketing are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Email Campaign - Marketing email campaign */
export type EmailCampaign = {
  id: string;
  tenant_id: string;
  campaign_code: string;
  campaign_name: string;
  subject: string;
  template_id?: string;
  status: string;
  scheduled_at?: string;
  sent_at?: string;
  recipient_count: number;
  opened_count: number;
  clicked_count: number;
  created_at: string;
  updated_at: string;
};

/** Email Campaign create request */
export type EmailCampaignCreate = {
  campaign_code: string;
  campaign_name: string;
  subject: string;
  template_id?: string;
  status: string;
  scheduled_at?: string;
};

/** Email Template - Reusable email template */
export type EmailTemplate = {
  id: string;
  tenant_id: string;
  template_code: string;
  template_name: string;
  subject: string;
  body_html: string;
  body_text?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

export const MODULE_API_PREFIX = '/api/v1/email-marketing';

export const ENDPOINTS = {
  CAMPAIGNS: {
    LIST: `${MODULE_API_PREFIX}/campaigns/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/campaigns/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/campaigns/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/campaigns/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/campaigns/${id}/` as const,
  },
  TEMPLATES: {
    LIST: `${MODULE_API_PREFIX}/templates/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/templates/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/templates/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/templates/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/templates/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
