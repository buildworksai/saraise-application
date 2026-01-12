/**
 * Backup Job Detail Page
 * 
 * Displays detailed information about a backup job.
 */
import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { backupRecoveryService } from '../services/backup-recovery-service';
import { ArrowLeft, HardDrive } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ErrorState } from '@/components/ui';

export const BackupJobDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: job, isLoading, error, refetch } = useQuery({
    queryKey: ['backup-job', id],
    queryFn: () => id ? backupRecoveryService.getBackupJob(id) : Promise.reject(new Error('No ID')),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load backup job. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="p-8">
        <div className="text-center">
          <p className="text-muted-foreground">Backup job not found</p>
          <Button onClick={() => navigate('/backup-recovery/jobs')} className="mt-4">
            Back to Backup Jobs
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate('/backup-recovery/jobs')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Backup Job Details</h1>
      </div>

      <Card className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <HardDrive className="w-8 h-8 text-primary" />
            <div>
              <h2 className="text-xl font-semibold capitalize">{job.backup_type} Backup</h2>
              <p className="text-sm text-muted-foreground">ID: {job.id}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <div className="mt-1">
                <StatusBadge status={job.status === 'completed' ? 'active' : job.status === 'failed' ? 'error' : 'inactive'} />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Backup Type</label>
              <div className="mt-1 text-sm capitalize">{job.backup_type}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Start Time</label>
              <div className="mt-1 text-sm">
                {job.start_time ? new Date(job.start_time).toLocaleString() : 'Not started'}
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">End Time</label>
              <div className="mt-1 text-sm">
                {job.end_time ? new Date(job.end_time).toLocaleString() : 'Not completed'}
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Size</label>
              <div className="mt-1 text-sm">
                {job.backup_size_bytes ? `${(job.backup_size_bytes / 1024 / 1024).toFixed(2)} MB` : 'N/A'}
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Storage Location</label>
              <div className="mt-1 text-sm break-all">{job.storage_location || 'N/A'}</div>
            </div>

            {job.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <div className="mt-1 text-sm">{job.description}</div>
              </div>
            )}

            {job.error_message && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-destructive">Error Message</label>
                <div className="mt-1 text-sm text-destructive">{job.error_message}</div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium text-muted-foreground">Created At</label>
              <div className="mt-1 text-sm">{new Date(job.created_at).toLocaleString()}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Updated At</label>
              <div className="mt-1 text-sm">{new Date(job.updated_at).toLocaleString()}</div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};
