/**
 * Auth Store Tests
 * 
 * Tests for authentication store (Zustand).
 */

import { describe, expect, it, beforeEach } from 'vitest';
import { useAuthStore } from './auth-store';
import type { User } from './auth-store';

describe('useAuthStore', () => {
  beforeEach(() => {
    // Reset store state
    useAuthStore.getState().logout();
  });

  it('should initialize with null user and not authenticated', () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.isLoading).toBe(false);
  });

  it('should login user and set authenticated', () => {
    const mockUser: User = {
      id: '1',
      email: 'test@example.com',
      username: 'testuser',
      is_staff: false,
      is_superuser: false,
      tenant_id: 'tenant-123',
      platform_role: null,
      tenant_role: 'tenant_admin',
    };

    useAuthStore.getState().login(mockUser);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
  });

  it('should logout user and clear authenticated', () => {
    const mockUser: User = {
      id: '1',
      email: 'test@example.com',
      username: 'testuser',
      is_staff: false,
      is_superuser: false,
      tenant_id: null,
      platform_role: null,
      tenant_role: null,
    };

    useAuthStore.getState().login(mockUser);
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('should set user and update authenticated status', () => {
    const mockUser: User = {
      id: '1',
      email: 'test@example.com',
      username: 'testuser',
      is_staff: false,
      is_superuser: false,
      tenant_id: null,
      platform_role: null,
      tenant_role: null,
    };

    useAuthStore.getState().setUser(mockUser);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(mockUser);
    expect(state.isAuthenticated).toBe(true);
  });

  it('should set user to null and clear authenticated', () => {
    const mockUser: User = {
      id: '1',
      email: 'test@example.com',
      username: 'testuser',
      is_staff: false,
      is_superuser: false,
      tenant_id: null,
      platform_role: null,
      tenant_role: null,
    };

    useAuthStore.getState().setUser(mockUser);
    useAuthStore.getState().setUser(null);

    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('should set loading state', () => {
    useAuthStore.getState().setLoading(true);
    expect(useAuthStore.getState().isLoading).toBe(true);

    useAuthStore.getState().setLoading(false);
    expect(useAuthStore.getState().isLoading).toBe(false);
  });

  it('should set authenticated state directly', () => {
    useAuthStore.getState().setAuthenticated(true);
    expect(useAuthStore.getState().isAuthenticated).toBe(true);

    useAuthStore.getState().setAuthenticated(false);
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});

