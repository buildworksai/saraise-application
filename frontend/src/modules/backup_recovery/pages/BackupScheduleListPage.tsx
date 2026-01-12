/**
 * Backup Schedule List Page
 * 
 * Displays all backup schedules with filtering and CRUD operations.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { backupRecoveryService } from '../services/backup-recovery-service';
import { Plus, Search, Clock } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const BackupScheduleListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);
  const [filterFrequency, setFilterFrequency] = useState<string>('all');
  const [filterActive, setFilterActive] = useState<string>('all');

  const { data: schedules, isLoading, error, refetch } = useQuery({
    queryKey: ['backup-schedules', deferredSearchTerm],
    queryFn: backupRecoveryService.listBackupSchedules,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => backupRecoveryService.deleteBackupSchedule(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backup-schedules'] });
      toast.success('Backup schedule deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete backup schedule. Please try again.');
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      isActive
        ? backupRecoveryService.activateBackupSchedule(id)
        : backupRecoveryService.deactivateBackupSchedule(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['backup-schedules'] });
      toast.success('Schedule updated successfully');
    },
    onError: () => {
      toast.error('Failed to update schedule. Please try again.');
    },
  });

  const filteredSchedules = schedules?.filter((schedule) => {
    const matchesSearch = deferredSearchTerm === '' || 
      schedule.description?.toLowerCase().includes(deferredSearchTerm.toLowerCase());
    
    const matchesFrequency = filterFrequency === 'all' || schedule.frequency === filterFrequency;
    const matchesActive = filterActive === 'all'
      ? true
      : filterActive === 'active'
      ? schedule.is_active
      : !schedule.is_active;

    return matchesSearch && matchesFrequency && matchesActive;
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this backup schedule?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  const handleToggleActive = async (id: string, isActive: boolean) => {
    await toggleActiveMutation.mutateAsync({ id, isActive: !isActive });
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
          message="Failed to load backup schedules. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  if (!filteredSchedules || filteredSchedules.length === 0) {
    if (schedules?.length === 0) {
      return (
        <div className="p-8">
          <div className="mb-6 flex items-center justify-between">
            <h1 className="text-3xl font-bold text-foreground">Backup Schedules</h1>
            <Button onClick={() => navigate('/backup-recovery/schedules/create')}>
              <Plus className="w-4 h-4 mr-2" />
              Create Schedule
            </Button>
          </div>
          <EmptyState
            icon={Clock}
            title="No backup schedules yet"
            description="Create your first backup schedule to automate backups."
            action={{
              label: "Create Schedule",
              onClick: () => navigate('/backup-recovery/schedules/create')
            }}
          />
        </div>
      );
    }
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Backup Schedules</h1>
        <Button onClick={() => navigate('/backup-recovery/schedules/create')}>
          <Plus className="w-4 h-4" />
          Create Schedule
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-6 flex gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-5 h-5" />
          <Input
            type="text"
            placeholder="Search schedules..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select
          value={filterFrequency}
          onChange={(e) => setFilterFrequency(e.target.value)}
          options={[
            { value: 'all', label: 'All Frequencies' },
            { value: 'hourly', label: 'Hourly' },
            { value: 'daily', label: 'Daily' },
            { value: 'weekly', label: 'Weekly' },
            { value: 'monthly', label: 'Monthly' },
          ]}
        />

        <Select
          value={filterActive}
          onChange={(e) => setFilterActive(e.target.value)}
          options={[
            { value: 'all', label: 'All Status' },
            { value: 'active', label: 'Active' },
            { value: 'inactive', label: 'Inactive' },
          ]}
        />
      </div>

      {/* Schedules Table */}
      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Frequency
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Backup Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Retention Days
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Created
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredSchedules?.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-muted-foreground">
                  No schedules found matching your filters
                </td>
              </tr>
            ) : (
              filteredSchedules?.map((schedule) => (
                <tr key={schedule.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="text-sm font-medium capitalize">{schedule.frequency}</div>
                    {schedule.schedule_time && (
                      <div className="text-sm text-muted-foreground">{schedule.schedule_time}</div>
                    )}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm capitalize">
                    {schedule.backup_type}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {schedule.retention_days} days
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={schedule.is_active ? 'active' : 'inactive'} />
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                    {new Date(schedule.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      onClick={() => navigate(`/backup-recovery/schedules/${schedule.id}`)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      View
                    </button>
                    <button
                      onClick={() => void handleToggleActive(schedule.id, schedule.is_active)}
                      className="text-primary hover:opacity-80 mr-4"
                    >
                      {schedule.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                    <button
                      onClick={() => {
                        void handleDelete(schedule.id);
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
