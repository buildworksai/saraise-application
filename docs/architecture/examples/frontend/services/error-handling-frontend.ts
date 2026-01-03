/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Frontend Error Handling
// frontend/src/services/error-handling-frontend.ts
// Reference: docs/architecture/security-model.md § 4.1 (Error Handling)
// CRITICAL NOTES:
// - Never expose internal error details to user interface (security-model.md § 4.1)
// - All error responses include: code, message, details, timestamp
// - AuthenticationError (401) indicates session expired - redirect to login
// - AuthorizationError (403) indicates Policy Engine denied request - show permission error
// - ValidationError (422) includes field-level errors for form display
// - ServerError (500) should not expose details - log server-side for investigation
// - Network errors should include retry logic with exponential backoff
// - Error messages MUST NOT contain sensitive data (paths, SQL, credentials)
// - All errors captured in client-side logging (with PII filtering)
// Source: docs/architecture/security-model.md § 4.1, operational-runbooks.md § 4.1

import { toast } from 'sonner'

export interface SARAISEError {
  code: string
  message: string
  details?: Record<string, any>
  timestamp: string
}

export interface APIErrorResponse {
  error: SARAISEError
}

export class SARAISEErrorHandler {
  static handle(error: any): void {
    console.error('SARAISE Error:', error)

    if (error.response?.data?.error) {
      const saraiseError = error.response.data.error as SARAISEError
      this.handleSARAISEError(saraiseError)
    } else if (error.message) {
      this.handleGenericError(error.message)
    } else {
      this.handleUnknownError()
    }
  }

  private static handleSARAISEError(error: SARAISEError): void {
    switch (error.code) {
      case 'AuthenticationError':
        this.handleAuthenticationError(error)
        break
      case 'AuthorizationError':
        this.handleAuthorizationError(error)
        break
      case 'ValidationError':
        this.handleValidationError(error)
        break
      case 'DatabaseError':
        this.handleDatabaseError(error)
        break
      case 'ExternalServiceError':
        this.handleExternalServiceError(error)
        break
      case 'TenantIsolationError':
        this.handleTenantIsolationError(error)
        break
      case 'AIAgentError':
        this.handleAIAgentError(error)
        break
      case 'WorkflowError':
        this.handleWorkflowError(error)
        break
      default:
        this.handleGenericError(error.message)
    }
  }

  private static handleAuthenticationError(error: SARAISEError): void {
    toast.error('Authentication Failed', {
      description: error.message,
      action: {
        label: 'Login',
        onClick: () => window.location.href = '/login'
      }
    })
  }

  private static handleAuthorizationError(error: SARAISEError): void {
    toast.error('Access Denied', {
      description: error.message,
      action: {
        label: 'Contact Admin',
        onClick: () => window.location.href = '/contact'
      }
    })
  }

  private static handleValidationError(error: SARAISEError): void {
    toast.error('Validation Error', {
      description: error.message
    })
  }

  private static handleDatabaseError(error: SARAISEError): void {
    toast.error('Database Error', {
      description: 'A database error occurred. Please try again later.'
    })
  }

  private static handleExternalServiceError(error: SARAISEError): void {
    toast.error('Service Unavailable', {
      description: 'An external service is currently unavailable. Please try again later.'
    })
  }

  private static handleTenantIsolationError(error: SARAISEError): void {
    toast.error('Tenant Access Error', {
      description: error.message
    })
  }

  private static handleAIAgentError(error: SARAISEError): void {
    toast.error('AI Agent Error', {
      description: error.message
    })
  }

  private static handleWorkflowError(error: SARAISEError): void {
    toast.error('Workflow Error', {
      description: error.message
    })
  }

  private static handleGenericError(message: string): void {
    toast.error('Error', {
      description: message
    })
  }

  private static handleUnknownError(): void {
    toast.error('Unknown Error', {
      description: 'An unexpected error occurred. Please try again.'
    })
  }
}

// React hook for error handling
export function useErrorHandler() {
  const handleError = (error: any) => {
    SARAISEErrorHandler.handle(error)
  }

  return { handleError }
// ✅ APPROVED: API Client with Centralized Error Handling
// Uses apiClient internally which handles all session management
export class APIClientWithErrorHandling {
  constructor(private apiClient: ApiClient) {}

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    try {
      // ApiClient automatically includes session cookies (credentials: 'include')
      // and handles 401/403 responses
      const result = await this.apiClient.get<T>(endpoint, options as any);
      return result;
    } catch (error) {
      // Handle errors from apiClient
      SARAISEErrorHandler.handle(error);
      throw error;
    }
  }

  async requestWithMethod<T>(
    endpoint: string,
    method: 'POST' | 'PUT' | 'DELETE',
    data?: any,
    options?: RequestInit
  ): Promise<T> {
    try {
      // ApiClient handles session management and authorization errors
      if (method === 'POST') {
        return await this.apiClient.post<T>(endpoint, data, options as any);
      } else if (method === 'PUT') {
        return await this.apiClient.put<T>(endpoint, data, options as any);
      } else if (method === 'DELETE') {
        return await this.apiClient.delete<T>(endpoint, options as any);
      }
      throw new Error(`Unsupported method: ${method}`);
    } catch (error) {
      SARAISEErrorHandler.handle(error);
      throw error;
    }
  }
}

