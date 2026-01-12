/**
 * Backup Schedule Detail Page
 * 
 * Displays detailed information about a backup schedule and allows editing.
 */
import { useQuery } from '@tanstack/react-query';
import { useParams, useNavigate } from 'react-router-dom';
import { backupRecoveryService } from '../services/backup-recovery-service';
import { ArrowLeft, Clock } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { ErrorState } from '@/components/ui';

export const BackupScheduleDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: schedule, isLoading, error, refetch } = useQuery({
    queryKey: ['backup-schedule', id],
    queryFn: () => id ? backupRecoveryService.getBackupSchedule(id) : Promise.reject(new Error('No ID')),
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
          message="Failed to load backup schedule. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!schedule) {
    return (
      <div className="p-8">
        <div className="text-center">
          <p className="text-muted-foreground">Backup schedule not found</p>
          <Button onClick={() => navigate('/backup-recovery/schedules')} className="mt-4">
            Back to Backup Schedules
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate('/backup-recovery/schedules')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Backup Schedule Details</h1>
      </div>

      <Card className="p-6">
        <div className="space-y-6">
          <div className="flex items-center gap-4">
            <Clock className="w-8 h-8 text-primary" />
            <div>
              <h2 className="text-xl font-semibold capitalize">{schedule.frequency} Schedule</h2>
              <p className="text-sm text-muted-foreground">ID: {schedule.id}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <div className="mt-1">
                <StatusBadge status={schedule.is_active ? 'active' : 'inactive'} />
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Frequency</label>
              <div className="mt-1 text-sm capitalize">{schedule.frequency}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Backup Type</label>
              <div className="mt-1 text-sm capitalize">{schedule.backup_type}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Schedule Time</label>
              <div className="mt-1 text-sm">{schedule.schedule_time || 'N/A'}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Retention Days</label>
              <div className="mt-1 text-sm">{schedule.retention_days} days</div>
            </div>

            {schedule.description && (
              <div className="col-span-2">
                <label className="text-sm font-medium text-muted-foreground">Description</label>
                <div className="mt-1 text-sm">{schedule.description}</div>
              </div>
            )}

            <div>
              <label className="text-sm font-medium text-muted-foreground">Created At</label>
              <div className="mt-1 text-sm">{new Date(schedule.created_at).toLocaleString()}</div>
            </div>

            <div>
              <label className="text-sm font-medium text-muted-foreground">Updated At</label>
              <div className="mt-1 text-sm">{new Date(schedule.updated_at).toLocaleString()}</div>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
};
