/**
 * Fixed Asset List Page - Fixed Assets
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { fixedAssetsService } from '../services/fixed-assets-service';
import type { FixedAsset } from '../contracts';

const MODULE_PATH = '/fixed-assets/assets';

export const FixedAssetListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: assets, isLoading, error, refetch } = useQuery({
    queryKey: ['fixed-assets'],
    queryFn: () => fixedAssetsService.listFixedAssets(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => fixedAssetsService.deleteFixedAsset(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
      toast.success('Fixed asset deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete fixed asset. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this fixed asset?')) {
      await deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <TableSkeleton rows={5} columns={5} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <ErrorState
          message="Failed to load fixed assets. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!assets || assets.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Fixed Assets</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Fixed Asset
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No fixed assets yet"
          description="Create your first fixed asset to get started."
          action={{
            label: 'Create Fixed Asset',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Fixed Assets</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Fixed Asset
        </Button>
      </div>

      <Card className="overflow-hidden">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Code
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Name
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Category
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Purchase Cost
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {assets.map((asset) => (
              <tr key={asset.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {asset.asset_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{asset.asset_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                  {asset.asset_category}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{asset.purchase_cost}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">
                  {asset.is_active ? 'Active' : 'Inactive'}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${asset.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(asset.id)}
                    className="text-destructive hover:opacity-80"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
};
