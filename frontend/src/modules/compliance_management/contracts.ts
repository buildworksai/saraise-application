/**
 * Compliance Management Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Compliance Management are defined here.
 *
 * TODO: This is a scaffold. API endpoints and types must be defined when:
 * 1. Backend API is implemented
 * 2. OpenAPI schema is generated
 * 3. Types are available in @/types/api
 *
 * SPDX-License-Identifier: Apache-2.0
 */

import type { components } from '@/types/api';

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

// TODO: Define types when backend API is implemented
// Example:
// export type Entity = components['schemas']['Entity'];
// export type EntityCreate = components['schemas']['EntityCreate'];
// export type EntityUpdate = components['schemas']['PatchedEntityRequest'];

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * Compliance Management API Endpoints
 *
 * TODO: Define actual endpoints when backend API is implemented.
 * All endpoints should be prefixed with /api/v1/compliance-management/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.ENTITIES.LIST);
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/compliance-management';

export const ENDPOINTS = {
  // TODO: Define actual endpoints when backend API is implemented
  // Example structure:
  // ENTITIES: {
  //   LIST: `${MODULE_API_PREFIX}/entities/`,
  //   DETAIL: (id: string) => `${MODULE_API_PREFIX}/entities/${id}/`,
  //   CREATE: `${MODULE_API_PREFIX}/entities/`,
  //   UPDATE: (id: string) => `${MODULE_API_PREFIX}/entities/${id}/`,
  //   DELETE: (id: string) => `${MODULE_API_PREFIX}/entities/${id}/`,
  // },
} as const;

// =============================================================================
// TYPE GUARDS - Use for runtime type checking
// =============================================================================

// TODO: Add type guards when types are defined

// =============================================================================
// EXAMPLES - Reference for agents writing new code
// =============================================================================

/**
 * TODO: Add usage examples when backend API is implemented
 */
