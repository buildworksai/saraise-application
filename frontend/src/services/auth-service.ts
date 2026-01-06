/**
 * Authentication Service
 * 
 * Handles authentication API calls.
 */
import { apiClient } from './api-client';
import type { User } from '../stores/auth-store';

export interface LoginRequest {
  email: string;
  password: string;
  mfa_token?: string;
}

export interface LoginResponse {
  user: User;
  session_id: string;
}

export interface CurrentUserResponse {
  user: User;
}

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
  company_name?: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export const authService = {
  /**
   * Login with email and password
   */
  login: async (credentials: LoginRequest): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>('/api/v1/auth/login/', credentials);
  },

  /**
   * Logout current session
   */
  logout: async (): Promise<void> => {
    return apiClient.post('/api/v1/auth/logout/');
  },

  /**
   * Get current authenticated user
   */
  getCurrentUser: async (): Promise<User> => {
    const res = await apiClient.get<CurrentUserResponse>('/api/v1/auth/me/');
    return res.user;
  },

  /**
   * Refresh session validity
   */
  refreshSession: async (): Promise<void> => {
    return apiClient.post('/api/v1/auth/refresh/');
  },

  /**
   * Register new user account
   */
  register: async (data: RegisterRequest): Promise<LoginResponse> => {
    return apiClient.post<LoginResponse>('/api/v1/auth/register/', data);
  },

  /**
   * Request password reset email
   */
  forgotPassword: async (data: ForgotPasswordRequest): Promise<void> => {
    return apiClient.post('/api/v1/auth/forgot-password/', data);
  },

  /**
   * Reset password with token
   */
  resetPassword: async (data: ResetPasswordRequest): Promise<void> => {
    return apiClient.post('/api/v1/auth/reset-password/', data);
  },
};

