/**
 * Edit Feature Flag Dialog
 * 
 * Dialog for editing existing feature flags.
 */
import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { platformService, type FeatureFlag, type FeatureFlagUpdate } from '../services/platform-service';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Dialog } from '@/components/ui/Dialog';

interface EditFeatureFlagDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  flag: FeatureFlag;
}

export const EditFeatureFlagDialog = ({ open, onOpenChange, flag }: EditFeatureFlagDialogProps) => {
  const queryClient = useQueryClient();
  const flagId = flag.id;
  const [formData, setFormData] = useState<FeatureFlagUpdate>({
    enabled: flag.enabled,
    description: flag.description ?? '',
    rollout_percentage: flag.rollout_percentage,
  });

  useEffect(() => {
    if (flag) {
      setFormData({
        enabled: flag.enabled,
        description: flag.description ?? '',
        rollout_percentage: flag.rollout_percentage,
      });
    }
  }, [flag]);

  const updateMutation = useMutation({
    mutationFn: (data: FeatureFlagUpdate) => {
      if (!flagId) {
        return Promise.reject(new Error('Missing feature flag ID'));
      }
      return platformService.featureFlags.update(flagId, data);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-feature-flags'] });
      toast.success('Feature flag updated successfully');
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(`Failed to update feature flag: ${error.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!flagId) {
      toast.error('Unable to update feature flag: missing ID');
      return;
    }
    updateMutation.mutate(formData);
  };

  return (
    <Dialog 
      open={open} 
      onOpenChange={onOpenChange}
      title="Edit Feature Flag"
      description={`Update the feature flag: ${flag.name}`}
      size="lg"
    >
      <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={flag.name}
                disabled
                className="bg-muted"
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
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Updating...' : 'Update Feature Flag'}
            </Button>
          </div>
        </form>
    </Dialog>
  );
};
