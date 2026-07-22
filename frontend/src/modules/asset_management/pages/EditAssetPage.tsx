import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import { ROUTES, type AssetUpdate } from '../contracts';
import { AssetForm } from '../components/AssetForm';
import { PageHeader, PageSkeleton, ProblemState } from '../components/AssetManagementUI';
import { assetQueryKeys, assetService } from '../services/asset-service';

export const EditAssetPage = () => {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const query = useQuery({
    queryKey: assetQueryKeys.asset(tenantId, id),
    queryFn: () => assetService.getAsset(id),
    enabled: Boolean(id),
  });
  const mutation = useMutation({
    mutationFn: (data: AssetUpdate) => assetService.updateAsset(id, data),
    onSuccess: (asset) => {
      void queryClient.invalidateQueries({ queryKey: assetQueryKeys.root(tenantId) });
      toast.success('Asset updated');
      navigate(ROUTES.ASSETS.DETAIL(asset.id));
    },
  });

  if (query.isLoading) return <PageSkeleton />;
  if (query.error || !query.data) {
    return <main className="p-4 sm:p-8"><ProblemState error={query.error ?? new Error('Asset unavailable')} onRetry={() => void query.refetch()} /></main>;
  }

  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title={`Edit ${query.data.asset_code}`}
        description="Update descriptive and depreciation-policy fields without altering calculated history."
        backLabel="Asset details"
        onBack={() => navigate(ROUTES.ASSETS.DETAIL(id))}
      />
      <AssetForm
        asset={query.data}
        pending={mutation.isPending}
        error={mutation.error}
        onCancel={() => navigate(ROUTES.ASSETS.DETAIL(id))}
        onSubmit={(data) => mutation.mutate(data as AssetUpdate)}
      />
    </main>
  );
};
