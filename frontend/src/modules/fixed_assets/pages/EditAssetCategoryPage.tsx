import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import type { AssetCategoryCreateRequest } from '../contracts';
import { CategoryForm } from '../components/AssetForms';
import { PageHeader, PageSkeleton, ProblemState } from '../components/FixedAssetsUI';
import { fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const EditAssetCategoryPage = () => {
  const { id = '' } = useParams(); const navigate = useNavigate(); const client = useQueryClient(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const query = useQuery({ queryKey: fixedAssetQueryKeys.category(tenantId, id), queryFn: () => fixedAssetsService.getCategory(id), enabled: Boolean(id) });
  const mutation = useMutation({ mutationFn: (data: AssetCategoryCreateRequest) => fixedAssetsService.updateCategory(id, { ...data, expected_version: query.data?.version ?? 0 }), onSuccess: (category) => { void client.invalidateQueries({ queryKey: fixedAssetQueryKeys.root(tenantId) }); toast.success('Category updated'); navigate(`/fixed-assets/categories/${category.id}`); } });
  if (query.isLoading) return <PageSkeleton/>;
  if (query.error || !query.data) return <main className="p-4 sm:p-8"><ProblemState error={query.error ?? new Error('Category unavailable')} onRetry={() => void query.refetch()}/></main>;
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title={`Edit ${query.data.code}`} description="Category codes become immutable after first use; active mappings remain tenant-validated." backLabel="Category" onBack={() => navigate(`/fixed-assets/categories/${id}`)}/><CategoryForm category={query.data} pending={mutation.isPending} error={mutation.error} onCancel={() => navigate(`/fixed-assets/categories/${id}`)} onSubmit={(data) => mutation.mutate(data)}/></main>;
};
