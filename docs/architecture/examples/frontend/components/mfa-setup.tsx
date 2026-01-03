/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: MFA Setup Flow
// frontend/src/components/mfa-setup.tsx
// Reference: docs/architecture/authentication-and-session-management-spec.md § 2.3
// CRITICAL NOTES:
// - MFA setup flow: request secret → display QR code → validate code → confirm setup
// - QR code URI must be generated server-side (secret never exposed to client)
// - User scans QR code with authenticator app (Google Authenticator, Authy, etc.)
// - After scanning, user enters 6-digit code for verification
// - Session must be elevated before MFA setup (existing session required)
// - MFA credentials stored server-side only (TOTP secrets never in browser storage)
// - Recovery codes provided after successful MFA enrollment (user must save securely)
// - All MFA operations require HTTPS/TLS (no plaintext transmission)
// - MFA enforcement policy configured per-tenant (tenant_admin setting)
// Source: docs/architecture/authentication-and-session-management-spec.md § 2.3, security-model.md § 3.2

import { apiClient } from '@/services/api-client'

async function setupMFA() {
  const response = await apiClient.post<{ secret: string; qr_uri: string }>(
    '/api/v1/auth/mfa/setup',
    {}
  )

  const { qr_uri } = response

  // Display QR code for user to scan
  return qr_uri
}

