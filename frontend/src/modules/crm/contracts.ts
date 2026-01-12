/**
 * CRM Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for CRM are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Lead entity */
export type Lead = {
  id: string;
  tenant_id: string;
  first_name: string;
  last_name: string;
  email?: string;
  phone?: string;
  company?: string;
  title?: string;
  score: number;
  grade: string;
  source?: string;
  campaign_id?: string;
  owner_id?: string;
  status: 'new' | 'contacted' | 'qualified' | 'converted' | 'lost';
  converted_at?: string;
  converted_to_opportunity_id?: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by?: string;
};

/** Lead create request */
export type LeadCreate = {
  first_name?: string;
  last_name: string;
  email?: string;
  phone?: string;
  company?: string;
  title?: string;
  source?: string;
  campaign_id?: string;
  owner_id?: string;
  status?: 'new' | 'contacted' | 'qualified' | 'converted' | 'lost';
  metadata?: Record<string, unknown>;
};

/** Lead update request (partial) */
export type LeadUpdate = Partial<LeadCreate>;

/** Lead scoring response */
export type LeadScoringResponse = {
  score: number;
  grade: string;
  bant_qualification?: Record<string, unknown>;
};

/** Account entity */
export type Account = {
  id: string;
  tenant_id: string;
  name: string;
  website?: string;
  industry?: string;
  employees?: number;
  annual_revenue?: string;
  parent_account_id?: string;
  billing_street?: string;
  billing_city?: string;
  billing_state?: string;
  billing_postal_code?: string;
  billing_country?: string;
  owner_id?: string;
  account_type: 'prospect' | 'customer' | 'partner';
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by?: string;
};

/** Account create request */
export type AccountCreate = {
  name: string;
  website?: string;
  industry?: string;
  employees?: number;
  annual_revenue?: string;
  parent_account_id?: string;
  billing_street?: string;
  billing_city?: string;
  billing_state?: string;
  billing_postal_code?: string;
  billing_country?: string;
  owner_id?: string;
  account_type?: 'prospect' | 'customer' | 'partner';
  metadata?: Record<string, unknown>;
};

/** Account update request (partial) */
export type AccountUpdate = Partial<AccountCreate>;

/** Account hierarchy tree node */
export type AccountHierarchyNode = {
  id: string;
  name: string;
  account_type: string;
  children?: AccountHierarchyNode[];
};

/** Contact entity */
export type Contact = {
  id: string;
  tenant_id: string;
  account_id: string;
  first_name?: string;
  last_name: string;
  email?: string;
  phone?: string;
  mobile?: string;
  title?: string;
  department?: string;
  linkedin?: string;
  twitter?: string;
  last_contacted_at?: string;
  engagement_score: number;
  owner_id?: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by?: string;
};

/** Contact create request */
export type ContactCreate = {
  account_id: string;
  first_name?: string;
  last_name: string;
  email?: string;
  phone?: string;
  mobile?: string;
  title?: string;
  department?: string;
  linkedin?: string;
  twitter?: string;
  owner_id?: string;
  metadata?: Record<string, unknown>;
};

/** Contact update request (partial) */
export type ContactUpdate = Partial<Omit<ContactCreate, 'account_id'>>;

/** Opportunity entity */
export type Opportunity = {
  id: string;
  tenant_id: string;
  account_id: string;
  primary_contact_id?: string;
  name: string;
  description?: string;
  amount: string;
  currency: string;
  probability: number;
  stage: 'prospecting' | 'qualification' | 'needs_analysis' | 'proposal' | 'negotiation' | 'closed_won' | 'closed_lost';
  close_date: string;
  product_ids: string[];
  competitors: string[];
  owner_id: string;
  status: 'open' | 'won' | 'lost';
  closed_at?: string;
  loss_reason?: string;
  converted_to_order_id?: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by?: string;
  last_activity_at?: string;
};

/** Opportunity create request */
export type OpportunityCreate = {
  account_id: string;
  primary_contact_id?: string;
  name: string;
  description?: string;
  amount: string;
  currency?: string;
  probability?: number;
  stage?: 'prospecting' | 'qualification' | 'needs_analysis' | 'proposal' | 'negotiation' | 'closed_won' | 'closed_lost';
  close_date: string;
  product_ids?: string[];
  competitors?: string[];
  owner_id: string;
  metadata?: Record<string, unknown>;
};

/** Opportunity update request (partial) */
export type OpportunityUpdate = Partial<Omit<OpportunityCreate, 'account_id'>>;

/** Opportunity create from lead conversion */
export type OpportunityCreateFromLead = {
  name?: string;
  amount: string;
  close_date?: string;
  stage?: string;
  probability?: number;
  account_id?: string;
  create_new_account?: boolean;
};

/** Activity entity */
export type Activity = {
  id: string;
  tenant_id: string;
  activity_type: 'call' | 'email' | 'meeting' | 'task' | 'note';
  related_to_type: 'Lead' | 'Contact' | 'Account' | 'Opportunity';
  related_to_id: string;
  subject: string;
  description?: string;
  outcome?: string;
  due_date?: string;
  completed: boolean;
  completed_at?: string;
  owner_id: string;
  external_id?: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  created_by?: string;
};

/** Activity create request */
export type ActivityCreate = {
  activity_type: 'call' | 'email' | 'meeting' | 'task' | 'note';
  related_to_type: 'Lead' | 'Contact' | 'Account' | 'Opportunity';
  related_to_id: string;
  subject: string;
  description?: string;
  outcome?: string;
  due_date?: string;
  owner_id: string;
  external_id?: string;
  metadata?: Record<string, unknown>;
};

/** Activity update request (partial) */
export type ActivityUpdate = Partial<Omit<ActivityCreate, 'related_to_type' | 'related_to_id'>>;

/** Forecast response */
export type Forecast = {
  total_pipeline_value: number;
  weighted_pipeline_value: number;
  opportunity_count: number;
  period_days: number;
};

/** Win rate response */
export type WinRate = {
  win_rate: number;
  won_count: number;
  lost_count: number;
  total_closed: number;
  period_days: number;
};

/** AI prediction response */
export type AIPrediction = {
  predicted_revenue: number;
  confidence: number;
  factors: string[];
  period_days: number;
};

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * CRM API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/crm/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.LEADS.LIST);
 * apiClient.get(ENDPOINTS.LEADS.DETAIL(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/crm';

export const ENDPOINTS = {
  LEADS: {
    LIST: `${MODULE_API_PREFIX}/leads/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/leads/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/` as const,
    CONVERT: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/convert/` as const,
    AI_SCORE: (id: string) => `${MODULE_API_PREFIX}/leads/${id}/ai-score/` as const,
  },
  ACCOUNTS: {
    LIST: `${MODULE_API_PREFIX}/accounts/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/accounts/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/` as const,
    HIERARCHY: (id: string) => `${MODULE_API_PREFIX}/accounts/${id}/hierarchy/` as const,
  },
  CONTACTS: {
    LIST: `${MODULE_API_PREFIX}/contacts/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/contacts/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/contacts/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/contacts/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/contacts/${id}/` as const,
  },
  OPPORTUNITIES: {
    LIST: `${MODULE_API_PREFIX}/opportunities/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/opportunities/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/` as const,
    CLOSE_WON: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/close-won/` as const,
    CLOSE_LOST: (id: string) => `${MODULE_API_PREFIX}/opportunities/${id}/close-lost/` as const,
  },
  ACTIVITIES: {
    LIST: `${MODULE_API_PREFIX}/activities/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/activities/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/` as const,
    COMPLETE: (id: string) => `${MODULE_API_PREFIX}/activities/${id}/complete/` as const,
  },
  FORECASTING: {
    PIPELINE: `${MODULE_API_PREFIX}/forecasting/pipeline/`,
    WIN_RATE: `${MODULE_API_PREFIX}/forecasting/win-rate/`,
    AI_PREDICT: `${MODULE_API_PREFIX}/forecasting/ai-predict/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

// =============================================================================
// TYPE GUARDS - Use for runtime type checking
// =============================================================================

/** Type guard for Lead */
export function isLead(obj: unknown): obj is Lead {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'last_name' in obj &&
    'score' in obj &&
    typeof (obj as Lead).score === 'number'
  );
}

/** Type guard for Account */
export function isAccount(obj: unknown): obj is Account {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'name' in obj &&
    'account_type' in obj
  );
}

/** Type guard for Opportunity */
export function isOpportunity(obj: unknown): obj is Opportunity {
  return (
    typeof obj === 'object' &&
    obj !== null &&
    'id' in obj &&
    'account_id' in obj &&
    'amount' in obj &&
    'stage' in obj
  );
}
