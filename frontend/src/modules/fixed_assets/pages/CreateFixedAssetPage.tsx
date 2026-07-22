import { useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import type { FixedAssetCreateRequest } from '../contracts';
import { AssetForm } from '../components/AssetForms';
import { EmptyPanel, PageHeader, PageSkeleton, ProblemState } from '../components/FixedAssetsUI';
import { createIdempotencyKey, fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const CreateFixedAssetPage = () => {
  const navigate = useNavigate(); const client = useQueryClient(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const idempotencyKey = useRef(createIdempotencyKey('create-asset'));
  const categories = useQuery({ queryKey: fixedAssetQueryKeys.categories(tenantId, { is_active: true, page_size: 100 }), queryFn: () => fixedAssetsService.listCategories({ is_active: true, page_size: 100 }) });
  const mutation = useMutation({ mutationFn: (data: FixedAssetCreateRequest) => fixedAssetsService.createAsset(data, idempotencyKey.current), onSuccess: (asset) => { void client.invalidateQueries({ queryKey: fixedAssetQueryKeys.root(tenantId) }); toast.success('Asset registered'); navigate(`/fixed-assets/assets/${asset.id}`); } });
  if (categories.isLoading) return <PageSkeleton/>;
  if (categories.error) return <main className="p-4 sm:p-8"><ProblemState error={categories.error} onRetry={() => void categories.refetch()}/></main>;
  if (!categories.data?.items.length) return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Register fixed asset" backLabel="Asset register" onBack={() => navigate('/fixed-assets/assets')}/><EmptyPanel title="An active category is required" description="Create and map a category before registering an asset." action={{ label: 'Create category', onClick: () => navigate('/fixed-assets/categories/new') }}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Register fixed asset" description="Balances and state are server-controlled; registration starts in draft." backLabel="Asset register" onBack={() => navigate('/fixed-assets/assets')}/><AssetForm categories={categories.data?.items ?? []} pending={mutation.isPending} error={mutation.error} onCancel={() => navigate('/fixed-assets/assets')} onSubmit={(data) => mutation.mutate(data as FixedAssetCreateRequest)}/></main>;
};
