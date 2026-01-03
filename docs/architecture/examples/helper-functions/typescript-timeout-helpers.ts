/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Timeout & Duration Helper Functions
// frontend/src/helpers/timeout-helpers.ts
// Reference: docs/architecture/authentication-and-session-management-spec.md § 3.2

export const getTimeouts = () => {
  /**
   * CRITICAL: Session timeout enforced on server via HTTP-only cookies.
   * Frontend timeout is UI/UX only - actual expiration happens server-side.
   * See docs/architecture/authentication-and-session-management-spec.md § 3.2.
   */
  return {
    session: parseInt(import.meta.env.VITE_SESSION_TIMEOUT || '7200'),
    api: parseInt(import.meta.env.VITE_API_TIMEOUT || '30'),
    toast: {
      info: parseInt(import.meta.env.VITE_TOAST_INFO_DURATION || '6'),
      warning: parseInt(import.meta.env.VITE_TOAST_WARNING_DURATION || '8'),
      error: parseInt(import.meta.env.VITE_TOAST_ERROR_DURATION || '10')
    },
    loading: parseInt(import.meta.env.VITE_LOADING_TIMEOUT || '15')
  };
};

export const getToastDuration = (severity: 'info' | 'warning' | 'error'): number => {
  const timeouts = getTimeouts();
  return timeouts.toast[severity];
};

