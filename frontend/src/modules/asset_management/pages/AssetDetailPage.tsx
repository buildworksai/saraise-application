/**
 * Asset Detail Page - Asset Management
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { assetService } from '../services/asset-service';

const MODULE_PATH = '/asset-management/assets';

export const AssetDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: asset, isLoading, error } = useQuery({
    queryKey: ['asset-asset', id],
    queryFn: () => (id ? assetService.getAsset(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (assetId: string) => assetService.deleteAsset(assetId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['asset-assets'] });
      toast.success('Asset deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete asset. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this asset?')) {
      void deleteMutation.mutateAsync(id);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4" />
          <div className="h-64 bg-muted rounded" />
        </div>
      </div>
    );
  }

  if (error || !asset) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Asset not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Assets</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate(MODULE_PATH)}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-3xl font-bold text-foreground">
            {asset.asset_code} - {asset.asset_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${asset.id}/edit`)}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Asset Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{asset.asset_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{asset.asset_name}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Category</label>
              <p className="text-sm">{asset.category}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Purchase Date</label>
              <p className="text-sm">{new Date(asset.purchase_date).toLocaleDateString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Purchase Cost</label>
              <p className="text-sm">{asset.purchase_cost}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Current Value</label>
              <p className="text-sm">{asset.current_value}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Depreciation Method</label>
              <p className="text-sm">{asset.depreciation_method}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{asset.is_active ? 'Active' : 'Inactive'}</p>
            </div>
            {asset.location && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Location</label>
                <p className="text-sm">{asset.location}</p>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(asset.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(asset.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
