/**
 * Localization Module Contracts
 *
 * Rule: SARAISE-27001 (contracts.ts required for all frontend modules)
 *
 * === AGENT INSTRUCTION ===
 * Read this file FIRST when working on this module.
 * All types and endpoints for Localization are defined here.
 */

// import type { components } from '@/types/api'; // Commented out until schema types are available

// =============================================================================
// EXPORTED TYPES - Import these in your components
// =============================================================================

/** Language entity */
export type Language = {
  id: string;
  code: string;
  name: string;
  native_name: string;
  is_rtl: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

/** Translation entity */
export type Translation = {
  id: string;
  tenant_id: string;
  language: string;
  language_id?: string;
  key: string;
  value: string;
  context?: string;
  created_at: string;
  updated_at: string;
};

/** Translation create request */
export type TranslationCreate = {
  language: string;
  key: string;
  value: string;
  context?: string;
};

/** Translation update request (partial) */
export type TranslationUpdate = Partial<TranslationCreate>;

/** LocaleConfig entity */
export type LocaleConfig = {
  id: string;
  tenant_id: string;
  default_language: string;
  default_language_id?: string;
  timezone: string;
  date_format: string;
  time_format: string;
  number_format: string;
  created_at: string;
  updated_at: string;
};

/** LocaleConfig create request */
export type LocaleConfigCreate = {
  default_language: string;
  timezone?: string;
  date_format?: string;
  time_format?: string;
  number_format?: string;
};

/** LocaleConfig update request (partial) */
export type LocaleConfigUpdate = Partial<LocaleConfigCreate>;

/** CurrencyConfig entity */
export type CurrencyConfig = {
  id: string;
  tenant_id: string;
  default_currency: string;
  exchange_rates: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

/** CurrencyConfig create request */
export type CurrencyConfigCreate = {
  default_currency: string;
  exchange_rates?: Record<string, unknown>;
};

/** CurrencyConfig update request (partial) */
export type CurrencyConfigUpdate = Partial<CurrencyConfigCreate>;

/** RegionalSettings entity */
export type RegionalSettings = {
  id: string;
  tenant_id: string;
  country_code: string;
  tax_settings: Record<string, unknown>;
  fiscal_year_start?: string;
  business_days: number[];
  created_at: string;
  updated_at: string;
};

/** RegionalSettings create request */
export type RegionalSettingsCreate = {
  country_code: string;
  tax_settings?: Record<string, unknown>;
  fiscal_year_start?: string;
  business_days?: number[];
};

/** RegionalSettings update request (partial) */
export type RegionalSettingsUpdate = Partial<RegionalSettingsCreate>;

// =============================================================================
// ENDPOINT REGISTRY - Use these for all API calls
// =============================================================================

/**
 * Localization API Endpoints
 *
 * All endpoints should be prefixed with /api/v1/localization/
 *
 * Usage:
 * ```typescript
 * import { ENDPOINTS } from './contracts';
 * apiClient.get(ENDPOINTS.LANGUAGES.LIST);
 * apiClient.get(ENDPOINTS.TRANSLATIONS.DETAIL(id));
 * ```
 */
export const MODULE_API_PREFIX = '/api/v1/localization';

export const ENDPOINTS = {
  LANGUAGES: {
    LIST: `${MODULE_API_PREFIX}/languages/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/languages/${id}/` as const,
  },
  TRANSLATIONS: {
    LIST: `${MODULE_API_PREFIX}/translations/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/translations/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/translations/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/translations/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/translations/${id}/` as const,
  },
  LOCALE_CONFIGS: {
    LIST: `${MODULE_API_PREFIX}/locale-configs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/locale-configs/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/locale-configs/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/locale-configs/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/locale-configs/${id}/` as const,
  },
  CURRENCY_CONFIGS: {
    LIST: `${MODULE_API_PREFIX}/currency-configs/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/currency-configs/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/currency-configs/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/currency-configs/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/currency-configs/${id}/` as const,
  },
  REGIONAL_SETTINGS: {
    LIST: `${MODULE_API_PREFIX}/regional-settings/`,
    DETAIL: (id: string) => `${MODULE_API_PREFIX}/regional-settings/${id}/` as const,
    CREATE: `${MODULE_API_PREFIX}/regional-settings/`,
    UPDATE: (id: string) => `${MODULE_API_PREFIX}/regional-settings/${id}/` as const,
    DELETE: (id: string) => `${MODULE_API_PREFIX}/regional-settings/${id}/` as const,
  },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;
