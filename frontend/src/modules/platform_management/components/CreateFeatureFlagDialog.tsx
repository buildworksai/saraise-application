/**
 * Create Feature Flag Dialog
 * 
 * Dialog for creating new feature flags.
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { platformService, type FeatureFlagCreate } from '../services/platform-service';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Dialog } from '@/components/ui/Dialog';

interface CreateFeatureFlagDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const CreateFeatureFlagDialog = ({ open, onOpenChange }: CreateFeatureFlagDialogProps) => {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<FeatureFlagCreate>({
    name: '',
    enabled: false,
    description: '',
    rollout_percentage: 100,
  });

  const createMutation = useMutation({
    mutationFn: (data: FeatureFlagCreate) => platformService.featureFlags.create(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-feature-flags'] });
      toast.success('Feature flag created successfully');
      onOpenChange(false);
      setFormData({
        name: '',
        enabled: false,
        description: '',
        rollout_percentage: 100,
      });
    },
    onError: (error: Error) => {
      toast.error(`Failed to create feature flag: ${error.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    createMutation.mutate(formData);
  };

  return (
    <Dialog 
      open={open} 
      onOpenChange={onOpenChange}
      title="Create Feature Flag"
      description="Create a new feature flag for gradual rollout and A/B testing."
      size="lg"
    >
      <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="feature_flag_name"
                required
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={formData.description ?? ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Feature flag description"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="rollout_percentage">Rollout Percentage (0-100)</Label>
              <Input
                id="rollout_percentage"
                type="number"
                min="0"
                max="100"
                value={formData.rollout_percentage}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  setFormData({
                    ...formData,
                    rollout_percentage: Number.isNaN(value) ? 0 : value,
                  });
                }}
                required
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="enabled"
                checked={formData.enabled}
                onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                className="h-4 w-4"
              />
              <Label htmlFor="enabled">Enabled</Label>
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Feature Flag'}
            </Button>
          </div>
        </form>
    </Dialog>
  );
};
