/**
 * Module Layout Component
 * 
 * Provides consistent layout for module pages with sidebar navigation,
 * header with user menu, and breadcrumbs.
 */
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navigation } from './Navigation';
import { useAuthStore } from '../../stores/auth-store';
import { authService } from '../../services/auth-service';
import { LogOut, User, Settings, Menu, X } from 'lucide-react';
import { useState } from 'react';
import { ThemeToggle } from '../ui/theme-toggle';

interface ModuleLayoutProps {
  children: ReactNode;
}

export const ModuleLayout = ({ children }: ModuleLayoutProps) => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const handleLogout = async () => {
    try {
      await authService.logout();
      logout();
      navigate('/login');
    } catch {
      // Even if API call fails, clear local state
      logout();
      navigate('/login');
    }
  };

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed lg:static inset-y-0 left-0 z-50 w-64
          transform transition-transform duration-300 ease-in-out
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
        `}
      >
        <Navigation />
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col w-full lg:w-auto">
        {/* Header */}
        <header className="bg-background border-b border-border px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* Mobile Menu Button */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 rounded-md hover:bg-accent"
                aria-label="Toggle sidebar"
              >
                {sidebarOpen ? (
                  <X className="w-6 h-6" />
                ) : (
                  <Menu className="w-6 h-6" />
                )}
              </button>
              {/* Breadcrumbs can be added here */}
            </div>

            {/* User Menu */}
            <div className="flex items-center gap-4">
              <ThemeToggle />
              <div className="relative">
                <button
                  onClick={() => setShowUserMenu(!showUserMenu)}
                  className="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors"
                >
                  <div className="w-8 h-8 bg-primary rounded-full flex items-center justify-center text-primary-foreground text-sm font-medium">
                    {user?.email?.[0]?.toUpperCase() ?? 'U'}
                  </div>
                  <span className="text-sm font-medium">{user?.email}</span>
                </button>

                {showUserMenu && (
                <>
                  <div
                    className="fixed inset-0 z-10"
                    onClick={() => setShowUserMenu(false)}
                  />
                  <div className="absolute right-0 mt-2 w-48 bg-popover text-popover-foreground rounded-md shadow-lg py-1 z-20 border border-border">
                    <div className="px-4 py-2 border-b border-border">
                      <div className="text-sm font-medium">{user?.email}</div>
                      {user?.tenant_id && (
                        <div className="text-xs text-muted-foreground mt-1">
                          Tenant: {user.tenant_id.slice(0, 8)}...
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => {
                        setShowUserMenu(false);
                        // TODO: Navigate to profile page
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
                    >
                      <User className="w-4 h-4" />
                      Profile
                    </button>
                    <button
                      onClick={() => {
                        setShowUserMenu(false);
                        // TODO: Navigate to settings page
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
                    >
                      <Settings className="w-4 h-4" />
                      Settings
                    </button>
                    <button
                      onClick={() => {
                        void handleLogout();
                      }}
                      className="w-full flex items-center gap-2 px-4 py-2 text-sm text-destructive hover:bg-destructive/10"
                    >
                      <LogOut className="w-4 h-4" />
                      Logout
                    </button>
                  </div>
                </>
              )}
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main id="main-content" className="flex-1 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
};
