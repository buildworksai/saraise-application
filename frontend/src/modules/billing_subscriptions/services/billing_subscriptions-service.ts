/**
 * BillingSubscriptions Service
 * 
 * Service client for BillingSubscriptions module API calls.
 * 
 * Uses contracts.ts for types and endpoints.
 */
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type Subscription, type SubscriptionCreate, type SubscriptionUpdate } from '../contracts';

export const billing_subscriptionsService = {
  /**
   * List all subscriptions
   */
  listSubscriptions: async (): Promise<Subscription[]> => {
    return apiClient.get<Subscription[]>(ENDPOINTS.SUBSCRIPTIONS.LIST);
  },

  /**
   * Get subscription by ID
   */
  getSubscription: async (id: string): Promise<Subscription> => {
    return apiClient.get<Subscription>(ENDPOINTS.SUBSCRIPTIONS.DETAIL(id));
  },

  /**
   * Create new subscription
   */
  createSubscription: async (data: SubscriptionCreate): Promise<Subscription> => {
    return apiClient.post<Subscription>(ENDPOINTS.SUBSCRIPTIONS.CREATE, data);
  },

  /**
   * Update subscription
   */
  updateSubscription: async (id: string, data: SubscriptionUpdate): Promise<Subscription> => {
    return apiClient.put<Subscription>(ENDPOINTS.SUBSCRIPTIONS.UPDATE(id), data);
  },

  /**
   * Delete subscription
   */
  deleteSubscription: async (id: string): Promise<void> => {
    return apiClient.delete(ENDPOINTS.SUBSCRIPTIONS.DELETE(id));
  },
};
