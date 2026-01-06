/**
 * Navigation Wrapper
 *
 * IMPORTANT: We maintain exactly two sidebars:
 * - PlatformSidebar: for platform-scoped users
 * - TenantSidebar: for tenant-scoped users
 *
 * This wrapper selects the correct sidebar based on the verified backend identity
 * stored in `useAuthStore().user`.
 */
import { useAuthStore } from '../../stores/auth-store';
import { PlatformSidebar } from './PlatformSidebar';
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

  if (user.platform_role) {
    return <PlatformSidebar user={user} />;
  }

  return <TenantSidebar user={user} />;
};

