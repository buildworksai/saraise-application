/**
 * Backup Archive Page
 * 
 * Displays all archived backups.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { backupRecoveryService } from '../services/backup-recovery-service';
import { Search, Archive } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const BackupArchivePage = () => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: archives, isLoading, error, refetch } = useQuery({
    queryKey: ['backup-archives', deferredSearchTerm],
    queryFn: backupRecoveryService.listBackupArchives,
  });

  const filteredArchives = archives?.filter((archive) => {
    return deferredSearchTerm === '' || 
      archive.archive_location.toLowerCase().includes(deferredSearchTerm.toLowerCase()) ||
      archive.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={6} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load backup archives. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredArchives || filteredArchives.length === 0) {
    if (archives?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6">
            <h1 className="text-3xl font-bold text-foreground">Backup Archives</h1>
          </div>
          <EmptyState
            icon={Archive}
            title="No archived backups yet"
            description="Archived backups will appear here once retention policies archive old backups."
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">Backup Archives</h1>
      </div>

      {/* Search */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search archives..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>
      </div>

      {/* Archives Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Backup Job
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Archive Location
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Size
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Archived At
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredArchives?.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-muted-foreground">
                  No archives found matching your search
                </td>
              </tr>
            ) : (
              filteredArchives?.map((archive) => (
                <tr key={archive.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium capitalize">{archive.backup_job.backup_type}</div>
                    <div className="text-sm text-muted-foreground">ID: {archive.backup_job.id}</div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm break-all">
                    {archive.archive_location}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {archive.archive_size_bytes ? `${(archive.archive_size_bytes / 1024 / 1024).toFixed(2)} MB` : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {new Date(archive.archived_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/backup-recovery/archives/${archive.id}`)}
                      className="text-primary hover:opacity-80"
                    >
                      View
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
