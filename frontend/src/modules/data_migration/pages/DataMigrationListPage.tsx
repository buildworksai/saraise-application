/**
 * Data Migration List Page
 * 
 * Displays all migration jobs with filtering, search, and CRUD operations.
 * Follows the same design pattern as WorkflowListPage.
 */
import { useState, useDeferredValue } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { migrationService } from '../services/migration-service';
import { MigrationJob } from '../contracts';
import { Plus, Search, DatabaseZap, Play, MoreVertical } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';

export const DataMigrationListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const deferredSearchTerm = useDeferredValue(searchTerm);

  const { data: jobs, isLoading, error, refetch } = useQuery({
    queryKey: ['migration-jobs', deferredSearchTerm],
    queryFn: migrationService.jobs.list,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => migrationService.jobs.delete(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['migration-jobs'] });
      toast.success('Migration job deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete migration job. Please try again.');
    },
  });

  const filteredJobs = jobs?.filter((job: MigrationJob) => {
    if (!deferredSearchTerm) return true;
    const name = String(job.name || '');
    return name.toLowerCase().includes(deferredSearchTerm.toLowerCase());
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this migration job?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  const handleExecute = async (id: string) => {
    try {
      await migrationService.jobs.execute(id);
      toast.success('Migration job started');
      void refetch();
    } catch (e) {
      toast.error('Failed to start migration job');
    }
  };

  const handleDryRun = async (id: string) => {
    try {
      await migrationService.jobs.dryRun(id);
      toast.success('Dry run completed');
      void refetch();
    } catch (e) {
      toast.error('Failed to run dry run');
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load migration jobs. Please check your connection and try again."
          onRetry={() => {
            void refetch();
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground">Data Migration</h1>
          <p className="text-muted-foreground">
            Manage and monitor data migration jobs
          </p>
        </div>
        <Button onClick={() => navigate('/data-migration/jobs/new')}>
          <Plus className="w-4 h-4 mr-2" />
          New Migration Job
        </Button>
      </div>

      {!filteredJobs || filteredJobs.length === 0 ? (
        <EmptyState
          icon={DatabaseZap}
          title="No migration jobs yet"
          description="Create your first migration job to import data."
          action={{
            label: 'Create Migration Job',
            onClick: () => navigate('/data-migration/jobs/new'),
          }}
        />
      ) : (
        <>
          <div className="mb-4">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <Input
                type="text"
                placeholder="Search migration jobs..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </div>

          <div className="grid gap-4">
            {filteredJobs.map((job: MigrationJob) => (
              <Card key={job.id} className="p-4 flex items-center justify-between hover:shadow-md transition-shadow">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="font-semibold text-lg text-foreground">{job.name}</h3>
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium border ${
                        job.status === 'completed'
                          ? 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20 dark:border-green-400/20'
                          : job.status === 'running'
                          ? 'bg-primary/10 text-primary border-primary/20'
                          : job.status === 'failed'
                          ? 'bg-destructive/10 text-destructive border-destructive/20'
                          : 'bg-muted text-muted-foreground border-border'
                      }`}
                    >
                      {job.status?.toUpperCase() || 'PENDING'}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <DatabaseZap className="w-4 h-4" />
                      {job.source_type?.toUpperCase() || 'CSV'}
                    </span>
                    {job.records_total > 0 && (
                      <>
                        <span>•</span>
                        <span>
                          {job.records_processed || 0} / {job.records_total} processed
                        </span>
                      </>
                    )}
                    {job.progress_percentage !== undefined && (
                      <>
                        <span>•</span>
                        <span>{job.progress_percentage}% complete</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  {job.status === 'pending' && (
                    <>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleDryRun(job.id)}
                      >
                        Dry Run
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleExecute(job.id)}
                      >
                        <Play className="w-4 h-4 mr-2" />
                        Execute
                      </Button>
                    </>
                  )}
                  {job.status === 'running' && (
                    <span className="text-sm text-muted-foreground">Running...</span>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/data-migration/jobs/${job.id}`)}
                  >
                    View
                  </Button>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
};
