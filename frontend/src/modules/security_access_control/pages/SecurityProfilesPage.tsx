/**
 * Security Profiles Page
 * 
 * Displays and manages security profiles.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { apiClient } from '@/services/api-client';
import { ENDPOINTS, SecurityProfile } from '../contracts';
import { Plus, Search, Shield } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const SecurityProfilesPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: profiles, isLoading, error, refetch } = useQuery({
    queryKey: ['security-profiles', deferredSearchTerm],
    queryFn: () => apiClient.get<SecurityProfile[]>(ENDPOINTS.SECURITY_PROFILES.LIST),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(ENDPOINTS.SECURITY_PROFILES.DELETE(id)),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['security-profiles'] });
      toast.success('Security profile deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete security profile. Please try again.');
    },
  });

  const filteredProfiles = profiles?.filter((profile) => {
    return deferredSearchTerm === '' || 
      profile.name.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      profile.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this security profile?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={5} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load security profiles. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredProfiles || filteredProfiles.length === 0) {
    if (profiles?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Security Profiles</h1>
            <Button onClick={() => navigate('/security-access-control/security-profiles/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Profile
            </Button>
          </div>
          <EmptyState
            icon={Shield}
            title="No security profiles yet"
            description="Create your first security profile to manage access controls."
            action={{
              label: "Create Profile",
              onClick: () => navigate('/security-access-control/security-profiles/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Security Profiles</h1>
        <Button onClick={() => navigate('/security-access-control/security-profiles/create')}>
          <Plus className="w-4 h-4" />
          Create Profile
        </Button>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search profiles..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Profiles Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                MFA Required
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Description
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredProfiles?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No profiles found matching your search
                </td>
              </tr>
            ) : (
              filteredProfiles?.map((profile) => (
                <tr key={profile.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium">{profile.name}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status="active" />
                    <div className="text-sm text-muted-foreground capitalize">{profile.profile_type}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm capitalize">
                    {profile.mfa_required}
                  </td>
                  <td className="px-6 py-4 text-sm text-muted-foreground">
                    {profile.description || 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/security-access-control/security-profiles/${profile.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(profile.id);
                      }}
                      className="text-destructive hover:opacity-80"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
