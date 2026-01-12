/**
 * Notifications Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 */

export type NotificationType = "info" | "success" | "warning" | "error" | "workflow" | "approval" | "system";

export interface Notification {
  id: string;
  tenant_id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  message: string;
  read: boolean;
  read_at: string | null;
  action_url: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface NotificationPreference {
  id: string;
  tenant_id: string;
  user_id: string;
  email_enabled: boolean;
  sms_enabled: boolean;
  push_enabled: boolean;
  in_app_enabled: boolean;
  workflow_notifications: boolean;
  approval_notifications: boolean;
  system_notifications: boolean;
  created_at: string;
  updated_at: string;
}

export const MODULE_API_PREFIX = "/api/v1/notifications";

export const ENDPOINTS = {
  NOTIFICATIONS: {
    LIST: `${MODULE_API_PREFIX}/notifications/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/notifications/${id}/`,
    MARK_READ: (id: string) => `${MODULE_API_PREFIX}/notifications/${id}/mark-read/`,
    MARK_ALL_READ: `${MODULE_API_PREFIX}/notifications/mark-all-read/`,
    UNREAD_COUNT: `${MODULE_API_PREFIX}/notifications/unread-count/`,
  },
  PREFERENCES: {
    GET: `${MODULE_API_PREFIX}/preferences/`,
    UPDATE: `${MODULE_API_PREFIX}/preferences/`,
  },
} as const;
