/**
 * Backup Job List Page
 * 
 * Displays all backup jobs with filtering, search, and CRUD operations.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { backupRecoveryService } from '../services/backup-recovery-service';
import { Plus, Search, HardDrive } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const BackupJobListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const [filterType, setFilterType] = useState<string>('all');
  const [filterStatus, setFilterStatus] = useState<string>('all');

  const { data: jobs, isLoading, error, refetch } = useQuery({
    queryKey: ['backup-jobs', deferredSearchTerm],
    queryFn: backupRecoveryService.listBackupJobs,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => backupRecoveryService.deleteBackupJob(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backup-jobs'] });
      toast.success('Backup job deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete backup job. Please try again.');
    },
  });

  const filteredJobs = jobs?.filter((job) => {
    const matchesSearch = deferredSearchTerm === '' || 
      job.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
    
    const matchesType = filterType === 'all' || job.backup_type === filterType;
    const matchesStatus = filterStatus === 'all' || job.status === filterStatus;

    return matchesSearch && matchesType && matchesStatus;
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this backup job?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

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
          message="Failed to load backup jobs. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredJobs || filteredJobs.length === 0) {
    if (jobs?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Backup Jobs</h1>
            <Button onClick={() => navigate('/backup-recovery/jobs/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Backup Job
            </Button>
          </div>
          <EmptyState
            icon={HardDrive}
            title="No backup jobs yet"
            description="Create your first backup job to protect your data."
            action={{
              label: "Create Backup Job",
              onClick: () => navigate('/backup-recovery/jobs/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Backup Jobs</h1>
        <Button onClick={() => navigate('/backup-recovery/jobs/create')}>
          <Plus className="w-4 h-4" />
          Create Backup Job
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search backup jobs..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          options={[
            { value: 'all', label: 'All Types' },
            { value: 'full', label: 'Full' },
            { value: 'incremental', label: 'Incremental' },
            { value: 'differential', label: 'Differential' },
          ]}
        />

        <Select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          options={[
            { value: 'all', label: 'All Status' },
            { value: 'pending', label: 'Pending' },
            { value: 'running', label: 'Running' },
            { value: 'completed', label: 'Completed' },
            { value: 'failed', label: 'Failed' },
          ]}
        />
      </div>

      {/* Jobs Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Size
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Start Time
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                End Time
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredJobs?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                  No backup jobs found matching your filters
                </td>
              </tr>
            ) : (
              filteredJobs?.map((job) => (
                <tr key={job.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium capitalize">{job.backup_type}</div>
                    {job.description && (
                      <div className="text-sm text-muted-foreground">{job.description}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={job.status === 'completed' ? 'active' : job.status === 'failed' ? 'error' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {job.backup_size_bytes ? `${(job.backup_size_bytes / 1024 / 1024).toFixed(2)} MB` : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {job.start_time ? new Date(job.start_time).toLocaleString() : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {job.end_time ? new Date(job.end_time).toLocaleString() : 'N/A'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/backup-recovery/jobs/${job.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(job.id);
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
