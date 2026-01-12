/**
 * Authentication Service
 *
 * Handles authentication API calls.
 *
 * MIGRATED: Now uses auth-contracts.ts for types and endpoints.
 * Reference: saraise-documentation/rules/agent-rules/27-contracts-architecture.md
 */
import { apiClient } from './api-client';
import type {
  LoginRequest,
  LoginResponse,
  CurrentUserResponse,
  RegisterRequest,
  ForgotPasswordRequest,
  ResetPasswordRequest,
  User,
} from './auth-contracts';
import { ENDPOINTS } from './auth-contracts';

// Re-export types for backward compatibility
export type {
  LoginRequest,
  LoginResponse,
  CurrentUserResponse,
  RegisterRequest,
  ForgotPasswordRequest,
  ResetPasswordRequest,
};

export const authService = {
  /**
   * Login with email and password
   */
  login: async (credentials: LoginRequest): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>(ENDPOINTS.LOGIN, credentials);
  },

  /**
   * Logout current session
   */
  logout: async (): Promise<void> => {
    return apiClient.post(ENDPOINTS.LOGOUT);
  },

  /**
   * Get current authenticated user
   */
  getCurrentUser: async (): Promise<User> => {
    const res = await apiClient.get<CurrentUserResponse>(ENDPOINTS.ME);
    return res.user;
  },

  /**
   * Refresh session validity
   */
  refreshSession: async (): Promise<void> => {
    return apiClient.post(ENDPOINTS.REFRESH);
  },

  /**
   * Register new user account
   */
  register: async (data: RegisterRequest): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>(ENDPOINTS.REGISTER, data);
  },

  /**
   * Request password reset email
   */
  forgotPassword: async (data: ForgotPasswordRequest): Promise<void> => {
    return apiClient.post(ENDPOINTS.FORGOT_PASSWORD, data);
  },

  /**
   * Reset password with token
   */
  resetPassword: async (data: ResetPasswordRequest): Promise<void> => {
    return apiClient.post(ENDPOINTS.RESET_PASSWORD, data);
  },
};
