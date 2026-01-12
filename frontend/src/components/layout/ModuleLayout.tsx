/**
 * Module Layout Component
 *
 * Provides consistent layout for module pages with sidebar navigation,
 * header with user menu, and breadcrumbs.
 *
 * Floating glass panel design with glassmorphism effects.
 */
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Navigation } from './Navigation';
import { MeshBackground } from './MeshBackground';
import { useAuthStore } from '../../stores/auth-store';
import { authService } from '../../services/auth-service';
import { LogOut, User, Settings, Menu, X, Bell } from 'lucide-react';
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

  // Extract display name: use username if different from email, otherwise extract from email
  const getDisplayName = () => {
    if (!user) return '';
    if (user.username && user.username.trim() !== '' && user.username !== user.email) {
      return user.username;
    }
    // Extract username from email (part before @)
    return user.email.split('@')[0];
  };

  const displayName = getDisplayName();

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
    <div className="min-h-screen bg-background text-foreground relative">
      <MeshBackground />
      <div className="flex h-screen overflow-hidden p-4 gap-4">
        {/* Mobile Sidebar Overlay */}
        {sidebarOpen && (
          <div
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={() => setSidebarOpen(false)}
          />
        )}

        {/* Sidebar - Glass Panel */}
        <aside
          className={`
            hidden md:flex flex-col w-64 glass border-white/10 shadow-2xl rounded-2xl
            transform transition-transform duration-300 ease-in-out
            ${sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}
            fixed md:static inset-y-0 left-0 z-50
          `}
        >
          <Navigation />
        </aside>

        {/* Main Content - Glass Panel */}
        <main className="flex-1 glass border-white/10 shadow-2xl rounded-2xl flex flex-col overflow-hidden">
          {/* Topbar */}
          <header className="sticky top-0 z-30 bg-background/50 backdrop-blur-md glass border-b border-white/10 px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                {/* Mobile Menu Button */}
                <button
                  onClick={() => setSidebarOpen(!sidebarOpen)}
                  className="md:hidden p-2 rounded-md hover:bg-white/10 transition-colors"
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
                <button className="relative p-2 rounded-md hover:bg-white/10 transition-colors">
                  <Bell className="w-5 h-5" />
                  <span className="absolute top-1 right-1 w-2 h-2 bg-deepBlue rounded-full animate-pulse" />
                </button>
                <div className="relative">
                  <button
                    onClick={() => setShowUserMenu(!showUserMenu)}
                    className="flex items-center gap-2 px-4 py-2 rounded-md hover:bg-white/10 transition-colors"
                  >
                    <div className="w-8 h-8 bg-deepBlue rounded-full flex items-center justify-center text-white text-sm font-medium border-2 border-deepBlue/30">
                      {(displayName && displayName[0]) ? displayName[0].toUpperCase() : 'U'}
                    </div>
                    <span className="text-sm font-medium hidden lg:inline">{displayName || 'User'}</span>
                  </button>

                  {showUserMenu && (
                    <>
                      <div
                        className="fixed inset-0 z-10"
                        onClick={() => setShowUserMenu(false)}
                      />
                      <div className="absolute right-0 mt-2 w-48 bg-popover text-popover-foreground rounded-md shadow-lg py-1 z-20 border border-border">
                        <div className="px-4 py-2 border-b border-border">
                          <div className="text-sm font-medium">{displayName}</div>
                          <div className="text-xs text-muted-foreground mt-1">
                            {user?.email}
                          </div>
                          {user?.tenant_id && (
                            <div className="text-xs text-muted-foreground mt-1">
                              Tenant: {user.tenant_id.slice(0, 8)}...
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => {
                            setShowUserMenu(false);
                            navigate('/profile');
                          }}
                          className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
                        >
                          <User className="w-4 h-4" />
                          Profile
                        </button>
                        <button
                          onClick={() => {
                            setShowUserMenu(false);
                            navigate('/settings');
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

          {/* Dashboard Content */}
          <div className="flex-1 overflow-auto p-6 scrollbar-hide">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};
