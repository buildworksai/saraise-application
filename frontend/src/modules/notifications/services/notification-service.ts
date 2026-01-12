/**
 * Notification Service
 */

import { apiClient } from '@/services/api-client';
import { ENDPOINTS, type Notification, type NotificationPreference } from '../contracts';

export const notificationService = {
  /**
   * Get user notifications
   */
  list: async (unreadOnly: boolean = false): Promise<Notification[]> => {
    return apiClient.get<Notification[]>(ENDPOINTS.NOTIFICATIONS.LIST, {
      params: { unread_only: unreadOnly },
    });
  },

  /**
   * Get notification by ID
   */
  get: async (id: string): Promise<Notification> => {
    return apiClient.get<Notification>(ENDPOINTS.NOTIFICATIONS.DETAIL(id));
  },

  /**
   * Mark notification as read
   */
  markRead: async (id: string): Promise<void> => {
    await apiClient.post(ENDPOINTS.NOTIFICATIONS.MARK_READ(id));
  },

  /**
   * Mark all notifications as read
   */
  markAllRead: async (): Promise<number> => {
    const response = await apiClient.post<{ count: number }>(ENDPOINTS.NOTIFICATIONS.MARK_ALL_READ);
    return response.count;
  },

  /**
   * Get unread notification count
   */
  getUnreadCount: async (): Promise<number> => {
    const response = await apiClient.get<{ count: number }>(ENDPOINTS.NOTIFICATIONS.UNREAD_COUNT);
    return response.count;
  },

  /**
   * Get user notification preferences
   */
  getPreferences: async (): Promise<NotificationPreference> => {
    return apiClient.get<NotificationPreference>(ENDPOINTS.PREFERENCES.GET);
  },

  /**
   * Update notification preferences
   */
  updatePreferences: async (preferences: Partial<NotificationPreference>): Promise<NotificationPreference> => {
    return apiClient.put<NotificationPreference>(ENDPOINTS.PREFERENCES.UPDATE, preferences);
  },
};
