/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: URL Construction Helper Functions
// frontend/src/helpers/url-helpers.ts
// Reference: docs/architecture/application-architecture.md § 6 (Deployment)

/**
 * CRITICAL: All URLs must be environment-configured via Vite.
 * No hardcoded URLs in code - use environment variables only.
 * See docs/architecture/application-architecture.md § 6.
 */

export const getApiUrl = (): string => {
  return import.meta.env.VITE_API_BASE_URL || `http://localhost:${import.meta.env.VITE_API_PORT || '20001'}`;
};

export const getFrontendUrl = (): string => {
  return import.meta.env.VITE_FRONTEND_BASE_URL || `http://localhost:${import.meta.env.VITE_FRONTEND_PORT || '20000'}`;
};

export const getMailhogUrl = (): string => {
  return import.meta.env.VITE_MAILHOG_URL || `http://localhost:${import.meta.env.VITE_MAILHOG_PORT || '20007'}`;
};

export const getVaultUrl = (): string => {
  return import.meta.env.VITE_VAULT_URL || `http://localhost:${import.meta.env.VITE_VAULT_PORT || '20008'}`;
};

export const getKongUrl = (): string => {
  return import.meta.env.VITE_KONG_URL || `http://localhost:${import.meta.env.VITE_KONG_PORT || '20013'}`;
};

export const getLokiUrl = (): string => {
  return import.meta.env.VITE_LOKI_URL || `http://localhost:${import.meta.env.VITE_LOKI_PORT || '20014'}`;
};

export const getPrometheusUrl = (): string => {
  return import.meta.env.VITE_PROMETHEUS_URL || `http://localhost:${import.meta.env.VITE_PROMETHEUS_PORT || '20009'}`;
};

export const getGrafanaUrl = (): string => {
  return import.meta.env.VITE_GRAFANA_URL || `http://localhost:${import.meta.env.VITE_GRAFANA_PORT || '20015'}`;
};

export const getFlowerUrl = (): string => {
  return import.meta.env.VITE_FLOWER_URL || `http://localhost:${import.meta.env.VITE_FLOWER_PORT || '20016'}`;
};

export const getEnvironmentUrls = () => {
  return {
    development: {
      frontend: getFrontendUrl(),
      api: getApiUrl(),
      mailhog: getMailhogUrl(),
      vault: getVaultUrl(),
      kong: getKongUrl(),
      loki: getLokiUrl(),
      prometheus: getPrometheusUrl(),
      grafana: getGrafanaUrl(),
      flower: getFlowerUrl()
    },
    staging: {
      base: import.meta.env.VITE_STAGING_BASE_URL || 'https://staging.saraise.com',
      api: import.meta.env.VITE_API_BASE_URL || 'https://api.saraise.com'
    },
    production: {
      base: import.meta.env.VITE_PRODUCTION_BASE_URL || 'https://saraise.com',
      api: import.meta.env.VITE_API_PRODUCTION_URL || 'https://api.saraise.com'
    }
  };
};

