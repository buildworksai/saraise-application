import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import { ROUTES, type AssetCreate } from '../contracts';
import { AssetForm } from '../components/AssetForm';
import { PageHeader } from '../components/AssetManagementUI';
import { assetQueryKeys, assetService } from '../services/asset-service';

export const CreateAssetPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const mutation = useMutation({
    mutationFn: (data: AssetCreate) => assetService.createAsset(data),
    onSuccess: (asset) => {
      void queryClient.invalidateQueries({ queryKey: assetQueryKeys.root(tenantId) });
      toast.success('Asset created');
      navigate(ROUTES.ASSETS.DETAIL(asset.id));
    },
  });

  return (
    <main className="space-y-6 p-4 sm:p-8">
      <PageHeader
        title="Create asset"
        description="Register acquisition facts and a depreciation policy. Calculated balances remain server-controlled."
        backLabel="Asset register"
        onBack={() => navigate(ROUTES.ASSETS.LIST)}
      />
      <AssetForm
        pending={mutation.isPending}
        error={mutation.error}
        onCancel={() => navigate(ROUTES.ASSETS.LIST)}
        onSubmit={(data) => mutation.mutate(data as AssetCreate)}
      />
    </main>
  );
};
