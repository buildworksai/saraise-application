/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Logging & Monitoring Helper Functions
// frontend/src/helpers/logging-helpers.ts
// Reference: docs/architecture/security-model.md § 4.2 (Audit Logging)

export const getLogLevel = (): string => {
  /**
   * CRITICAL: Frontend logging must respect server authorization decisions.
   * Client-side logging is NOT authoritative - backend is the source of truth.
   * See docs/architecture/security-model.md § 4.2.
   */
  const env = import.meta.env.MODE || 'development';
  const levelMap = {
    'development': import.meta.env.VITE_LOG_LEVEL_DEVELOPMENT || 'DEBUG',
    'staging': import.meta.env.VITE_LOG_LEVEL_STAGING || 'INFO',
    'production': import.meta.env.VITE_LOG_LEVEL_PRODUCTION || 'WARN'
  };
  return levelMap[env as keyof typeof levelMap] || 'INFO';
};

export const getMonitoringConfig = () => {
  return {
    prometheus: {
      enabled: import.meta.env.VITE_PROMETHEUS_ENABLED === 'true',
      port: parseInt(import.meta.env.VITE_PROMETHEUS_PORT || '19090')
    },
    grafana: {
      enabled: import.meta.env.VITE_GRAFANA_ENABLED === 'true',
      port: parseInt(import.meta.env.VITE_GRAFANA_PORT || '13000')
    },
    healthCheck: {
      interval: parseInt(import.meta.env.VITE_HEALTH_CHECK_INTERVAL || '60'),
      timeout: parseInt(import.meta.env.VITE_HEALTH_CHECK_TIMEOUT || '30')
    }
  };
};

