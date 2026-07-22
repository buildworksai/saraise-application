import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import type { ScheduleUpdateRequest } from '../contracts';
import { ScheduleForm } from '../components/ScheduleForm';
import { PageHeader, PageSkeleton, ProblemState } from '../components/FixedAssetsUI';
import { fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const EditDepreciationSchedulePage = () => {
  const { id = '' } = useParams(); const navigate = useNavigate(); const client = useQueryClient(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const schedule = useQuery({ queryKey: fixedAssetQueryKeys.schedule(tenantId, id), queryFn: () => fixedAssetsService.getSchedule(id), enabled: Boolean(id) });
  const assets = useQuery({ queryKey: fixedAssetQueryKeys.assets(tenantId, { page_size: 100 }), queryFn: () => fixedAssetsService.listAssets({ page_size: 100 }) });
  const mutation = useMutation({ mutationFn: (data: ScheduleUpdateRequest) => fixedAssetsService.updateSchedule(id, data), onSuccess: (saved) => { void client.invalidateQueries({ queryKey: fixedAssetQueryKeys.root(tenantId) }); toast.success('Schedule assumptions updated'); navigate(`/fixed-assets/depreciation-schedules/${saved.id}`); } });
  if (schedule.isLoading || assets.isLoading) return <PageSkeleton/>; if (schedule.error || assets.error || !schedule.data) return <main className="p-4 sm:p-8"><ProblemState error={schedule.error ?? assets.error ?? new Error('Schedule unavailable')} onRetry={() => { void schedule.refetch(); void assets.refetch(); }}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={`Edit ${schedule.data.schedule_number}`} description="Only draft assumptions are mutable. Posted history always creates a new revision." backLabel="Schedule" onBack={() => navigate(`/fixed-assets/depreciation-schedules/${id}`)}/><ScheduleForm schedule={schedule.data} assets={assets.data?.items ?? []} pending={mutation.isPending} error={mutation.error} onCancel={() => navigate(`/fixed-assets/depreciation-schedules/${id}`)} onSubmit={(data) => mutation.mutate(data as ScheduleUpdateRequest)}/></main>;
};
