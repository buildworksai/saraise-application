/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: MFA Verification
// frontend/src/services/mfa-verification.ts
// Reference: docs/architecture/authentication-and-session-management-spec.md § 2.3
// CRITICAL NOTES:
// - MFA codes transmitted via custom X-MFA-Code header (never in body)
// - Session cookie must include 'credentials: include' for every request
// - 428 status code indicates MFA required (step-up authentication required)
// - MFA state stored server-side only - never cache on client
// - After MFA verification, session is automatically upgraded (transparent to client)
// - Multiple failed MFA attempts should trigger rate limiting (security-model.md § 3.2)
// - All MFA verification requests must be over HTTPS/TLS only
// Source: docs/architecture/authentication-and-session-management-spec.md § 2.3, security-model.md § 3.2

async function deleteWithMFA(endpoint: string, mfaCode: string) {
  // ✅ APPROVED: MFA verification uses apiClient with custom headers
  // MFA codes transmitted via custom X-MFA-Code header (never in body)
  // Session cookie automatically included via apiClient (credentials: 'include')
  // 428 status code indicates step-up authentication required (MFA not satisfied)
  
  const apiClient = getApiClient(); // Get injected apiClient instance
  
  try {
    return await apiClient.delete<any>(endpoint, {
      headers: {
        'X-MFA-Code': mfaCode
      }
    });
  } catch (error: any) {
    if (error.response?.status === 428) {
      throw new Error('MFA required');
    }
    throw error;
  }
}

