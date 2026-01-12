/**
 * CRM Service
 *
 * Service client for CRM module API calls.
 *
 * Uses contracts.ts for types and endpoints.
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */

import { apiClient } from '@/services/api-client';
import type {
  Account,
  AccountCreate,
  AccountHierarchyNode,
  AccountUpdate,
  Activity,
  ActivityCreate,
  ActivityUpdate,
  AIPrediction,
  Contact,
  ContactCreate,
  ContactUpdate,
  Forecast,
  Lead,
  LeadCreate,
  LeadScoringResponse,
  LeadUpdate,
  Opportunity,
  OpportunityCreate,
  OpportunityCreateFromLead,
  OpportunityUpdate,
  WinRate,
} from '../contracts';
import { ENDPOINTS } from '../contracts';

// Re-export types for use in components
export type {
  Account,
  AccountCreate,
  AccountHierarchyNode,
  AccountUpdate,
  Activity,
  ActivityCreate,
  ActivityUpdate,
  AIPrediction,
  Contact,
  ContactCreate,
  ContactUpdate,
  Forecast,
  Lead,
  LeadCreate,
  LeadScoringResponse,
  LeadUpdate,
  Opportunity,
  OpportunityCreate,
  OpportunityCreateFromLead,
  OpportunityUpdate,
  WinRate,
};

export const crmService = {
  // =============================================================================
  // Lead Operations
  // =============================================================================

  /**
   * List all leads
   */
  listLeads: async (params?: {
    status?: string;
    owner_id?: string;
    score_min?: number;
    search?: string;
  }): Promise<Lead[]> => {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.append('status', params.status);
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);
    if (params?.score_min) queryParams.append('score_min', params.score_min.toString());
    if (params?.search) queryParams.append('search', params.search);

    const queryString = queryParams.toString();
    const url = queryString ? `${ENDPOINTS.LEADS.LIST}?${queryString}` : ENDPOINTS.LEADS.LIST;
    return apiClient.get<Lead[]>(url);
  },

  /**
   * Get lead by ID
   */
  getLead: async (id: string): Promise<Lead> => {
    return apiClient.get<Lead>(ENDPOINTS.LEADS.DETAIL(id));
  },

  /**
   * Create new lead
   */
  createLead: async (data: LeadCreate): Promise<Lead> => {
    return apiClient.post<Lead>(ENDPOINTS.LEADS.CREATE, data);
  },

  /**
   * Update lead
   */
  updateLead: async (id: string, data: LeadUpdate): Promise<Lead> => {
    return apiClient.patch<Lead>(ENDPOINTS.LEADS.UPDATE(id), data);
  },

  /**
   * Delete lead
   */
  deleteLead: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.LEADS.DELETE(id));
  },

  /**
   * Convert lead to opportunity
   */
  convertLead: async (id: string, data: OpportunityCreateFromLead): Promise<Opportunity> => {
    return apiClient.post<Opportunity>(ENDPOINTS.LEADS.CONVERT(id), data);
  },

  /**
   * Run AI scoring on lead
   */
  scoreLead: async (id: string): Promise<LeadScoringResponse> => {
    return apiClient.post<LeadScoringResponse>(ENDPOINTS.LEADS.AI_SCORE(id));
  },

  // =============================================================================
  // Account Operations
  // =============================================================================

  /**
   * List all accounts
   */
  listAccounts: async (params?: {
    account_type?: string;
    owner_id?: string;
    search?: string;
  }): Promise<Account[]> => {
    const queryParams = new URLSearchParams();
    if (params?.account_type) queryParams.append('account_type', params.account_type);
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);
    if (params?.search) queryParams.append('search', params.search);

    const queryString = queryParams.toString();
    const url = queryString ? `${ENDPOINTS.ACCOUNTS.LIST}?${queryString}` : ENDPOINTS.ACCOUNTS.LIST;
    return apiClient.get<Account[]>(url);
  },

  /**
   * Get account by ID
   */
  getAccount: async (id: string): Promise<Account> => {
    return apiClient.get<Account>(ENDPOINTS.ACCOUNTS.DETAIL(id));
  },

  /**
   * Create new account
   */
  createAccount: async (data: AccountCreate): Promise<Account> => {
    return apiClient.post<Account>(ENDPOINTS.ACCOUNTS.CREATE, data);
  },

  /**
   * Update account
   */
  updateAccount: async (id: string, data: AccountUpdate): Promise<Account> => {
    return apiClient.patch<Account>(ENDPOINTS.ACCOUNTS.UPDATE(id), data);
  },

  /**
   * Delete account
   */
  deleteAccount: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ACCOUNTS.DELETE(id));
  },

  /**
   * Get account hierarchy tree
   */
  getAccountHierarchy: async (id: string): Promise<AccountHierarchyNode> => {
    return apiClient.get<AccountHierarchyNode>(ENDPOINTS.ACCOUNTS.HIERARCHY(id));
  },

  // =============================================================================
  // Contact Operations
  // =============================================================================

  /**
   * List all contacts
   */
  listContacts: async (params?: {
    account_id?: string;
    owner_id?: string;
  }): Promise<Contact[]> => {
    const queryParams = new URLSearchParams();
    if (params?.account_id) queryParams.append('account_id', params.account_id);
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);

    const queryString = queryParams.toString();
    const url = queryString ? `${ENDPOINTS.CONTACTS.LIST}?${queryString}` : ENDPOINTS.CONTACTS.LIST;
    return apiClient.get<Contact[]>(url);
  },

  /**
   * Get contact by ID
   */
  getContact: async (id: string): Promise<Contact> => {
    return apiClient.get<Contact>(ENDPOINTS.CONTACTS.DETAIL(id));
  },

  /**
   * Create new contact
   */
  createContact: async (data: ContactCreate): Promise<Contact> => {
    return apiClient.post<Contact>(ENDPOINTS.CONTACTS.CREATE, data);
  },

  /**
   * Update contact
   */
  updateContact: async (id: string, data: ContactUpdate): Promise<Contact> => {
    return apiClient.patch<Contact>(ENDPOINTS.CONTACTS.UPDATE(id), data);
  },

  /**
   * Delete contact
   */
  deleteContact: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.CONTACTS.DELETE(id));
  },

  // =============================================================================
  // Opportunity Operations
  // =============================================================================

  /**
   * List all opportunities
   */
  listOpportunities: async (params?: {
    status?: string;
    stage?: string;
    owner_id?: string;
    account_id?: string;
  }): Promise<Opportunity[]> => {
    const queryParams = new URLSearchParams();
    if (params?.status) queryParams.append('status', params.status);
    if (params?.stage) queryParams.append('stage', params.stage);
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);
    if (params?.account_id) queryParams.append('account_id', params.account_id);

    const queryString = queryParams.toString();
    const url = queryString
      ? `${ENDPOINTS.OPPORTUNITIES.LIST}?${queryString}`
      : ENDPOINTS.OPPORTUNITIES.LIST;
    return apiClient.get<Opportunity[]>(url);
  },

  /**
   * Get opportunity by ID
   */
  getOpportunity: async (id: string): Promise<Opportunity> => {
    return apiClient.get<Opportunity>(ENDPOINTS.OPPORTUNITIES.DETAIL(id));
  },

  /**
   * Create new opportunity
   */
  createOpportunity: async (data: OpportunityCreate): Promise<Opportunity> => {
    return apiClient.post<Opportunity>(ENDPOINTS.OPPORTUNITIES.CREATE, data);
  },

  /**
   * Update opportunity
   */
  updateOpportunity: async (id: string, data: OpportunityUpdate): Promise<Opportunity> => {
    return apiClient.patch<Opportunity>(ENDPOINTS.OPPORTUNITIES.UPDATE(id), data);
  },

  /**
   * Delete opportunity
   */
  deleteOpportunity: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.OPPORTUNITIES.DELETE(id));
  },

  /**
   * Close opportunity as won
   */
  closeOpportunityWon: async (id: string): Promise<Opportunity> => {
    return apiClient.post<Opportunity>(ENDPOINTS.OPPORTUNITIES.CLOSE_WON(id), {});
  },

  /**
   * Close opportunity as lost
   */
  closeOpportunityLost: async (id: string, lossReason: string): Promise<Opportunity> => {
    return apiClient.post<Opportunity>(ENDPOINTS.OPPORTUNITIES.CLOSE_LOST(id), {
      loss_reason: lossReason,
    });
  },

  // =============================================================================
  // Activity Operations
  // =============================================================================

  /**
   * List all activities
   */
  listActivities: async (params?: {
    related_to_type?: string;
    related_to_id?: string;
    owner_id?: string;
  }): Promise<Activity[]> => {
    const queryParams = new URLSearchParams();
    if (params?.related_to_type) queryParams.append('related_to_type', params.related_to_type);
    if (params?.related_to_id) queryParams.append('related_to_id', params.related_to_id);
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);

    const queryString = queryParams.toString();
    const url = queryString
      ? `${ENDPOINTS.ACTIVITIES.LIST}?${queryString}`
      : ENDPOINTS.ACTIVITIES.LIST;
    return apiClient.get<Activity[]>(url);
  },

  /**
   * Get activity by ID
   */
  getActivity: async (id: string): Promise<Activity> => {
    return apiClient.get<Activity>(ENDPOINTS.ACTIVITIES.DETAIL(id));
  },

  /**
   * Create new activity
   */
  createActivity: async (data: ActivityCreate): Promise<Activity> => {
    return apiClient.post<Activity>(ENDPOINTS.ACTIVITIES.CREATE, data);
  },

  /**
   * Update activity
   */
  updateActivity: async (id: string, data: ActivityUpdate): Promise<Activity> => {
    return apiClient.patch<Activity>(ENDPOINTS.ACTIVITIES.UPDATE(id), data);
  },

  /**
   * Delete activity
   */
  deleteActivity: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.ACTIVITIES.DELETE(id));
  },

  /**
   * Mark activity as complete
   */
  completeActivity: async (id: string): Promise<Activity> => {
    return apiClient.post<Activity>(ENDPOINTS.ACTIVITIES.COMPLETE(id));
  },

  // =============================================================================
  // Forecasting Operations
  // =============================================================================

  /**
   * Get weighted pipeline forecast
   */
  getPipeline: async (params?: {
    owner_id?: string;
    period?: number;
  }): Promise<Forecast> => {
    const queryParams = new URLSearchParams();
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);
    if (params?.period) queryParams.append('period', params.period.toString());

    const queryString = queryParams.toString();
    const url = queryString
      ? `${ENDPOINTS.FORECASTING.PIPELINE}?${queryString}`
      : ENDPOINTS.FORECASTING.PIPELINE;
    return apiClient.get<Forecast>(url);
  },

  /**
   * Get historical win rate
   */
  getWinRate: async (params?: {
    owner_id?: string;
    period?: number;
  }): Promise<WinRate> => {
    const queryParams = new URLSearchParams();
    if (params?.owner_id) queryParams.append('owner_id', params.owner_id);
    if (params?.period) queryParams.append('period', params.period.toString());

    const queryString = queryParams.toString();
    const url = queryString
      ? `${ENDPOINTS.FORECASTING.WIN_RATE}?${queryString}`
      : ENDPOINTS.FORECASTING.WIN_RATE;
    return apiClient.get<WinRate>(url);
  },

  /**
   * Get AI-predicted revenue
   */
  getAIPrediction: async (params?: { period?: number }): Promise<AIPrediction> => {
    const queryParams = new URLSearchParams();
    if (params?.period) queryParams.append('period', params.period.toString());

    const queryString = queryParams.toString();
    const url = queryString
      ? `${ENDPOINTS.FORECASTING.AI_PREDICT}?${queryString}`
      : ENDPOINTS.FORECASTING.AI_PREDICT;
    return apiClient.get<AIPrediction>(url);
  },
};
