import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import type { FixedAssetUpdateRequest } from '../contracts';
import { AssetForm } from '../components/AssetForms';
import { PageHeader, PageSkeleton, ProblemState } from '../components/FixedAssetsUI';
import { fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const EditFixedAssetPage = () => {
  const { id = '' } = useParams(); const navigate = useNavigate(); const client = useQueryClient(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const asset = useQuery({ queryKey: fixedAssetQueryKeys.asset(tenantId, id), queryFn: () => fixedAssetsService.getAsset(id), enabled: Boolean(id) });
  const categories = useQuery({ queryKey: fixedAssetQueryKeys.categories(tenantId, { page_size: 100 }), queryFn: () => fixedAssetsService.listCategories({ page_size: 100 }) });
  const mutation = useMutation({ mutationFn: (data: FixedAssetUpdateRequest) => fixedAssetsService.updateAsset(id, data), onSuccess: (saved) => { void client.invalidateQueries({ queryKey: fixedAssetQueryKeys.root(tenantId) }); toast.success('Draft asset updated'); navigate(`/fixed-assets/assets/${saved.id}`); } });
  if (asset.isLoading || categories.isLoading) return <PageSkeleton/>;
  if (asset.error || categories.error || !asset.data) return <main className="p-4 sm:p-8"><ProblemState error={asset.error ?? categories.error ?? new Error('Asset unavailable')} onRetry={() => { void asset.refetch(); void categories.refetch(); }}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={`Edit ${asset.data.asset_code}`} description="Only draft assets can be edited; optimistic concurrency prevents lost changes." backLabel="Asset" onBack={() => navigate(`/fixed-assets/assets/${id}`)}/><AssetForm asset={asset.data} categories={categories.data?.items ?? []} pending={mutation.isPending} error={mutation.error} onCancel={() => navigate(`/fixed-assets/assets/${id}`)} onSubmit={(data) => mutation.mutate(data as FixedAssetUpdateRequest)}/></main>;
};
