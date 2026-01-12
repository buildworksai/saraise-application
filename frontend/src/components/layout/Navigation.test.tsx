/**
 * Navigation Component Tests
 *
 * ⚠️ ARCHITECTURAL ENFORCEMENT: Application repo is tenant-only.
 * Platform management UI MUST be in saraise-platform/frontend/.
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Navigation } from './Navigation';
import { useAuthStore } from '@/stores/auth-store';

// Mock sidebar
vi.mock('./TenantSidebar', () => ({
  TenantSidebar: ({ user }: { user: any }) => <div>Tenant Sidebar for {user.email}</div>,
}));

// Mock auth store
vi.mock('@/stores/auth-store', () => ({
  useAuthStore: vi.fn(),
}));

describe('Navigation', () => {
  it('should render empty shell when user is not available', () => {
    vi.mocked(useAuthStore).mockReturnValue({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      setUser: vi.fn(),
      setAuthenticated: vi.fn(),
      setLoading: vi.fn(),
    });

    render(<Navigation />);
    expect(screen.getByText('SARAISE')).toBeInTheDocument();
  });

  it('should render TenantSidebar for all users (application is tenant-only)', () => {
    const mockUser = {
      id: '1',
      email: 'tenant@example.com',
      username: 'tenant',
      is_staff: false,
      is_superuser: false,
      tenant_id: 'tenant-123',
      platform_role: null,
      tenant_role: 'tenant_admin',
    };

    vi.mocked(useAuthStore).mockReturnValue({
      user: mockUser,
      isAuthenticated: true,
      isLoading: false,
      login: vi.fn(),
      logout: vi.fn(),
      setUser: vi.fn(),
      setAuthenticated: vi.fn(),
      setLoading: vi.fn(),
    });

    render(<Navigation />);
    expect(screen.getByText(/tenant sidebar/i)).toBeInTheDocument();
  });
});
