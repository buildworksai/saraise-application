/**
 * Navigation Component Tests
 */

import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Navigation } from './Navigation';
import { useAuthStore } from '@/stores/auth-store';

// Mock sidebars
vi.mock('./PlatformSidebar', () => ({
  PlatformSidebar: ({ user }: { user: any }) => <div>Platform Sidebar for {user.email}</div>,
}));

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

  it('should render PlatformSidebar for platform users', () => {
    const mockUser = {
      id: '1',
      email: 'platform@example.com',
      username: 'platform',
      is_staff: true,
      is_superuser: true,
      tenant_id: null,
      platform_role: 'platform_owner',
      tenant_role: null,
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
    expect(screen.getByText(/platform sidebar/i)).toBeInTheDocument();
  });

  it('should render TenantSidebar for tenant users', () => {
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

