import { useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuthStore } from '@/stores/auth-store';
import type { AssetCategoryCreateRequest } from '../contracts';
import { CategoryForm } from '../components/AssetForms';
import { PageHeader } from '../components/FixedAssetsUI';
import { createIdempotencyKey, fixedAssetQueryKeys, fixedAssetsService } from '../services/fixed-assets-service';

export const CreateAssetCategoryPage = () => {
  const navigate = useNavigate(); const client = useQueryClient(); const tenantId = useAuthStore((state) => state.user?.tenant_id ?? null);
  const idempotencyKey = useRef(createIdempotencyKey('create-category'));
  const mutation = useMutation({ mutationFn: (data: AssetCategoryCreateRequest) => fixedAssetsService.createCategory(data, idempotencyKey.current), onSuccess: (category) => { void client.invalidateQueries({ queryKey: fixedAssetQueryKeys.root(tenantId) }); toast.success('Category created'); navigate(`/fixed-assets/categories/${category.id}`); } });
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create asset category" description="Set financial defaults and accounting mappings once for consistent asset registration." backLabel="Categories" onBack={() => navigate('/fixed-assets/categories')}/><CategoryForm pending={mutation.isPending} error={mutation.error} onCancel={() => navigate('/fixed-assets/categories')} onSubmit={(data) => mutation.mutate(data)}/></main>;
};
