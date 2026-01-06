/**
 * Create Setting Dialog
 * 
 * Dialog for creating new platform settings.
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { platformService, type PlatformSettingCreate } from '../services/platform-service';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Dialog } from '@/components/ui/Dialog';
import { Select } from '@/components/ui/Select';

interface CreateSettingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const CreateSettingDialog = ({ open, onOpenChange }: CreateSettingDialogProps) => {
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<PlatformSettingCreate>({
    key: '',
    value: '',
    category: 'general',
    description: '',
    is_secret: false,
    data_type: 'string',
  });

  const createMutation = useMutation({
    mutationFn: (data: PlatformSettingCreate) => platformService.settings.create(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-settings'] });
      toast.success('Setting created successfully');
      onOpenChange(false);
      setFormData({
        key: '',
        value: '',
        category: 'general',
        description: '',
        is_secret: false,
        data_type: 'string',
      });
    },
    onError: (error: Error) => {
      toast.error(`Failed to create setting: ${error.message}`);
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
      title="Create Platform Setting"
      description="Create a new platform-wide or tenant-specific configuration setting."
      size="lg"
    >
      <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="key">Key *</Label>
              <Input
                id="key"
                value={formData.key}
                onChange={(e) => setFormData({ ...formData, key: e.target.value })}
                placeholder="setting_key"
                required
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="value">Value *</Label>
              <Input
                id="value"
                value={formData.value}
                onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                placeholder="setting_value"
                required
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="category">Category</Label>
              <Input
                id="category"
                value={formData.category}
                onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                placeholder="general"
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="data_type">Data Type</Label>
              <Select
                value={formData.data_type}
                onChange={(e) => {
                  const value = e.target.value as PlatformSettingCreate['data_type'];
                  setFormData({ ...formData, data_type: value });
                }}
                options={[
                  { value: 'string', label: 'String' },
                  { value: 'integer', label: 'Integer' },
                  { value: 'boolean', label: 'Boolean' },
                  { value: 'json', label: 'JSON' },
                ]}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="description">Description</Label>
              <Input
                id="description"
                value={formData.description ?? ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Setting description"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_secret"
                checked={formData.is_secret}
                onChange={(e) => setFormData({ ...formData, is_secret: e.target.checked })}
                className="h-4 w-4"
              />
              <Label htmlFor="is_secret">Mark as secret (value will be masked)</Label>
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-4">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? 'Creating...' : 'Create Setting'}
            </Button>
          </div>
        </form>
    </Dialog>
  );
};
