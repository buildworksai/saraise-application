/**
 * ProtectedRoute Component Tests
 *
 * Tests for authentication-protected route component.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { useAuthStore } from '../../stores/auth-store';
import { authService } from '../../services/auth-service';

// Mock auth service
vi.mock('../../services/auth-service', () => ({
  authService: {
    getCurrentUser: vi.fn(),
  },
}));

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store state
    act(() => {
      useAuthStore.getState().logout();
      useAuthStore.getState().setLoading(false);
    });
  });

  it('should render children when authenticated', () => {
    const mockUser = {
      id: '1',
      email: 'test@example.com',
      username: 'test',
      is_staff: false,
      is_superuser: false,
      tenant_id: null,
      platform_role: null,
      tenant_role: null,
    };

    act(() => {
      useAuthStore.getState().login(mockUser);
    });

    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>,
    );

    expect(screen.getByText('Protected Content')).toBeInTheDocument();
  });

  it('should redirect to login when not authenticated', () => {
    act(() => {
      useAuthStore.getState().logout();
    });

    render(
      <MemoryRouter initialEntries={['/protected']}>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>,
    );

    // Should redirect (Navigate component behavior)
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
  });

  it('should show loading when verifying session', () => {
    act(() => {
      useAuthStore.getState().setLoading(true);
    });

    render(
      <MemoryRouter>
        <ProtectedRoute>
          <div>Protected Content</div>
        </ProtectedRoute>
      </MemoryRouter>,
    );

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should verify session on mount when no user', async () => {
    act(() => {
      useAuthStore.getState().logout();
    });

    const mockUser = {
      id: '1',
      email: 'test@example.com',
      username: 'test',
      is_staff: false,
      is_superuser: false,
      tenant_id: null,
      platform_role: null,
      tenant_role: null,
    };

    vi.mocked(authService.getCurrentUser).mockResolvedValueOnce(mockUser);

    await act(async () => {
      render(
        <MemoryRouter>
          <ProtectedRoute>
            <div>Protected Content</div>
          </ProtectedRoute>
        </MemoryRouter>,
      );
    });

    await waitFor(() => {
      expect(authService.getCurrentUser).toHaveBeenCalled();
    });
  });
});
