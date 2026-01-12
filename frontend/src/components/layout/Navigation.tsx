/**
 * Navigation Wrapper
 *
 * ⚠️ ARCHITECTURAL ENFORCEMENT: Application repo is tenant-only.
 * Platform management UI MUST be in saraise-platform/frontend/.
 *
 * This application frontend serves tenant-scoped users only.
 */
import { useAuthStore } from '../../stores/auth-store';
import { TenantSidebar } from './TenantSidebar';

export const Navigation = () => {
  const { user } = useAuthStore();

  // During initial bootstrap we may have a brief moment where user is not populated yet.
  // Keep layout stable (no "mystery sidebar") by rendering an empty shell.
  if (!user) {
    return (
      <nav className="bg-card text-card-foreground w-64 min-h-screen p-4 border-r border-border">
        <div className="mb-8">
          <h1 className="text-xl font-bold">SARAISE</h1>
        </div>
      </nav>
    );
  }

  // Application repo is tenant-only - always use TenantSidebar
  return <TenantSidebar user={user} />;
};
