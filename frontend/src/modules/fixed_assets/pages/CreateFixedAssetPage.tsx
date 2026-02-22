/**
 * Create Fixed Asset Page - Fixed Assets
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { fixedAssetsService } from '../services/fixed-assets-service';
import type { FixedAssetCreate } from '../contracts';

const MODULE_PATH = '/fixed-assets/assets';

export const CreateFixedAssetPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FixedAssetCreate>({
    asset_code: '',
    asset_name: '',
    asset_category: 'equipment',
    purchase_date: new Date().toISOString().split('T')[0] ?? '',
    purchase_cost: '0',
    current_value: '0',
    depreciation_method: 'straight_line',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: FixedAssetCreate) => fixedAssetsService.createFixedAsset(data),
    onSuccess: (asset) => {
      void queryClient.invalidateQueries({ queryKey: ['fixed-assets'] });
      toast.success('Fixed asset created successfully');
      navigate(`${MODULE_PATH}/${asset.id}`);
    },
    onError: () => {
      toast.error('Failed to create fixed asset. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.asset_code.trim() ||
      !form.asset_name.trim() ||
      !form.asset_category.trim() ||
      !form.purchase_date ||
      !form.purchase_cost.trim() ||
      !form.current_value.trim() ||
      !form.depreciation_method.trim()
    ) {
      toast.error(
        'Code, name, category, purchase date, cost, value, and depreciation method are required'
      );
      return;
    }
    createMutation.mutate(form);
  };

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate(MODULE_PATH)}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Create Fixed Asset</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Fixed Asset Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Asset Code</label>
              <Input
                value={form.asset_code}
                onChange={(e) => setForm({ ...form, asset_code: e.target.value })}
                placeholder="e.g. FA001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Asset Name</label>
              <Input
                value={form.asset_name}
                onChange={(e) => setForm({ ...form, asset_name: e.target.value })}
                placeholder="Asset name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Asset Category</label>
              <Input
                value={form.asset_category}
                onChange={(e) => setForm({ ...form, asset_category: e.target.value })}
                placeholder="e.g. equipment, vehicle"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Purchase Date</label>
              <Input
                type="date"
                value={form.purchase_date}
                onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-2 block">Purchase Cost</label>
                <Input
                  value={form.purchase_cost}
                  onChange={(e) => setForm({ ...form, purchase_cost: e.target.value })}
                  placeholder="0"
                  required
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-2 block">Current Value</label>
                <Input
                  value={form.current_value}
                  onChange={(e) => setForm({ ...form, current_value: e.target.value })}
                  placeholder="0"
                  required
                />
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Depreciation Method</label>
              <Input
                value={form.depreciation_method}
                onChange={(e) => setForm({ ...form, depreciation_method: e.target.value })}
                placeholder="e.g. straight_line"
                required
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Fixed Asset'}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate(MODULE_PATH)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
