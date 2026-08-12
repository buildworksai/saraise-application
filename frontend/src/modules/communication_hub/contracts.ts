/**
 * Communication Hub Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Communication Hub are defined here.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

export type ChannelType = string;
export type MessageType = string;
export type MessageStatus = string;

export interface CommunicationChannel {
  readonly id: string;
  readonly tenant_id: string;
  readonly channel_code: string;
  readonly channel_name: string;
  readonly channel_type: ChannelType;
  readonly is_active: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CommunicationMessage {
  readonly id: string;
  readonly tenant_id: string;
  readonly channel: string;
  readonly channel_code: string;
  readonly channel_name: string;
  readonly sender_id: string;
  readonly recipient_id: string | null;
  readonly subject: string;
  readonly body: string;
  readonly message_type: MessageType;
  readonly status: MessageStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ListEnvelope<T> {
  readonly count?: number;
  readonly next?: string | null;
  readonly previous?: string | null;
  readonly results?: readonly T[];
}

export const MODULE_API_PREFIX = "/api/v1/communication-hub";

export const ENDPOINTS = {
  CHANNELS: {
    LIST: `${MODULE_API_PREFIX}/channels/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/channels/${id}/`,
  },
  MESSAGES: {
    LIST: `${MODULE_API_PREFIX}/messages/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/messages/${id}/`,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const ROUTES = {
  CHANNELS: "/communication-hub",
  MESSAGES: "/communication-hub/messages",
  TEMPLATES: "/communication-hub/templates",
  CONFIGURATION: "/communication-hub/configuration",
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isCommunicationChannel(value: unknown): value is CommunicationChannel {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.tenant_id === "string" &&
    typeof value.channel_code === "string" &&
    typeof value.channel_name === "string" &&
    typeof value.channel_type === "string" &&
    typeof value.is_active === "boolean" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

export function isCommunicationMessage(value: unknown): value is CommunicationMessage {
  return (
    isRecord(value) &&
    typeof value.id === "string" &&
    typeof value.tenant_id === "string" &&
    typeof value.channel === "string" &&
    typeof value.channel_code === "string" &&
    typeof value.channel_name === "string" &&
    typeof value.sender_id === "string" &&
    (typeof value.recipient_id === "string" || value.recipient_id === null) &&
    typeof value.subject === "string" &&
    typeof value.body === "string" &&
    typeof value.message_type === "string" &&
    typeof value.status === "string" &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

/**
 * Backend limitation, July 2026:
 * communication_hub exposes channels, messages, and health only. Templates and
 * configuration routes render governed unavailable pages until matching
 * backend endpoints are implemented.
 */
