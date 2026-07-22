import { useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import type { ScheduleCreateRequest } from '../contracts';
import { ScheduleForm } from '../components/ScheduleForm';
import { EmptyPanel, PageHeader, PageSkeleton, ProblemState } from '../components/FixedAssetsUI';
import { createIdempotencyKey, fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const CreateDepreciationSchedulePage = () => {
  const navigate = useNavigate(); const [params] = useSearchParams(); const client = useQueryClient(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const idempotencyKey = useRef(createIdempotencyKey('create-schedule'));
  const assets = useQuery({ queryKey: fixedAssetQueryKeys.assets(tenantId, { status: 'active', page_size: 100 }), queryFn: () => fixedAssetsService.listAssets({ status: 'active', page_size: 100 }) });
  const mutation = useMutation({ mutationFn: (data: ScheduleCreateRequest) => fixedAssetsService.createSchedule(data, idempotencyKey.current), onSuccess: (schedule) => { void client.invalidateQueries({ queryKey: fixedAssetQueryKeys.root(tenantId) }); toast.success('Draft schedule created'); navigate(`/fixed-assets/depreciation-schedules/${schedule.id}`); } });
  if (assets.isLoading) return <PageSkeleton/>; if (assets.error) return <main className="p-4 sm:p-8"><ProblemState error={assets.error} onRetry={() => void assets.refetch()}/></main>;
  if (!assets.data?.items.length) return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create depreciation schedule" backLabel="Schedules" onBack={() => navigate('/fixed-assets/depreciation-schedules')}/><EmptyPanel title="No active assets are ready" description="Register and capitalize an asset before creating its depreciation schedule." action={{ label: 'View assets', onClick: () => navigate('/fixed-assets/assets') }}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create depreciation schedule" description="Start with server-owned asset assumptions, then calculate a complete preview before activation." backLabel="Schedules" onBack={() => navigate('/fixed-assets/depreciation-schedules')}/><ScheduleForm assets={assets.data?.items ?? []} defaultAssetId={params.get('asset_id') ?? undefined} pending={mutation.isPending} error={mutation.error} onCancel={() => navigate('/fixed-assets/depreciation-schedules')} onSubmit={(data) => mutation.mutate(data as ScheduleCreateRequest)}/></main>;
};
