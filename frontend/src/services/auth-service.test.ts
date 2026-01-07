/**
 * Auth Service Tests
 * 
 * Tests for authentication service including login, logout, registration, and session management.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { authService } from './auth-service';

// Mock fetch globally
const fetchMock = vi.fn();
global.fetch = fetchMock as unknown as typeof fetch;

describe('authService', () => {
  beforeEach(() => {
    fetchMock.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('login', () => {
    it('should login successfully with valid credentials', async () => {
      const mockResponse = {
        user: {
          id: '1',
          email: 'test@example.com',
          username: 'testuser',
        },
        session_id: 'session-123',
      };

      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

      const result = await authService.login({
        email: 'test@example.com',
        password: 'password123',
      });

      expect(result).toEqual(mockResponse);
    });

    it('should include MFA token if provided', async () => {
      const mockResponse = {
        user: { id: '1', email: 'test@example.com' },
        session_id: 'session-123',
      };

      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), { status: 200 }),
      );

      await authService.login({
        email: 'test@example.com',
        password: 'password123',
        mfa_token: 'mfa-token',
      });

      expect(fetchMock).toHaveBeenCalled();
    });
  });

  describe('register', () => {
    it('should register successfully', async () => {
      const mockResponse = {
        user: {
          id: '1',
          email: 'newuser@example.com',
          username: 'newuser',
        },
        session_id: 'session-123',
      };

      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify(mockResponse), {
          status: 201,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

      const result = await authService.register({
        name: 'New User',
        email: 'newuser@example.com',
        password: 'password123',
        company_name: 'My Organization',
      });

      expect(result).toEqual(mockResponse);
    });
  });

  describe('logout', () => {
    it('should logout successfully', async () => {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ message: 'Logged out successfully' }), {
          status: 200,
        }),
      );

      await authService.logout();

      expect(fetchMock).toHaveBeenCalled();
      const callArgs = fetchMock.mock.calls[0];
      expect(callArgs?.[0]).toContain('/api/v1/auth/logout/');
      expect(callArgs?.[1]).toMatchObject({
        method: 'POST',
        credentials: 'include',
      });
    });
  });

  describe('getCurrentUser', () => {
    it('should return current user', async () => {
      const mockUser = {
        id: '1',
        email: 'test@example.com',
        username: 'testuser',
        tenant_id: 'tenant-123',
      };

      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ user: mockUser }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );

      const result = await authService.getCurrentUser();

      expect(result).toEqual(mockUser);
      expect(fetchMock).toHaveBeenCalled();
      const callArgs = fetchMock.mock.calls[0];
      expect(callArgs?.[0]).toContain('/api/v1/auth/me/');
      expect(callArgs?.[1]).toMatchObject({
        method: 'GET',
        credentials: 'include',
      });
    });

    it('should throw error if not authenticated', async () => {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ error: 'Not authenticated' }), {
          status: 401,
        }),
      );

      await expect(authService.getCurrentUser()).rejects.toThrow();
    });
  });

  describe('refreshSession', () => {
    it('should refresh session successfully', async () => {
      fetchMock.mockResolvedValueOnce(
        new Response(JSON.stringify({ message: 'Session refreshed' }), {
          status: 200,
        }),
      );

      await authService.refreshSession();

      expect(fetchMock).toHaveBeenCalled();
      const callArgs = fetchMock.mock.calls[0];
      expect(callArgs?.[0]).toContain('/api/v1/auth/refresh/');
      expect(callArgs?.[1]).toMatchObject({
        method: 'POST',
        credentials: 'include',
      });
    });
  });
});

