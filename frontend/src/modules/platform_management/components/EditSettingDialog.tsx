/**
 * Edit Setting Dialog
 * 
 * Dialog for editing existing platform settings.
 */
import { useState, useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { platformService, type PlatformSetting, type PlatformSettingUpdate } from '../services/platform-service';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Dialog } from '@/components/ui/Dialog';
import { Select } from '@/components/ui/Select';

interface EditSettingDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  setting: PlatformSetting;
}

export const EditSettingDialog = ({ open, onOpenChange, setting }: EditSettingDialogProps) => {
  const queryClient = useQueryClient();
  const settingId = setting.id;
  const [formData, setFormData] = useState<PlatformSettingUpdate>({
    value: setting.value,
    category: setting.category,
    description: setting.description ?? '',
    is_secret: setting.is_secret,
    data_type: setting.data_type,
  });

  useEffect(() => {
    if (setting) {
      setFormData({
        value: setting.value,
        category: setting.category,
        description: setting.description ?? '',
        is_secret: setting.is_secret,
        data_type: setting.data_type,
      });
    }
  }, [setting]);

  const updateMutation = useMutation({
    mutationFn: (data: PlatformSettingUpdate) => {
      if (!settingId) {
        return Promise.reject(new Error('Missing setting ID'));
      }
      return platformService.settings.update(settingId, data);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['platform-settings'] });
      toast.success('Setting updated successfully');
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(`Failed to update setting: ${error.message}`);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!settingId) {
      toast.error('Unable to update setting: missing ID');
      return;
    }
    updateMutation.mutate(formData);
  };

  return (
    <Dialog 
      open={open} 
      onOpenChange={onOpenChange}
      title="Edit Platform Setting"
      description={`Update the platform setting: ${setting.key}`}
      size="lg"
    >
      <form onSubmit={handleSubmit}>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="key">Key</Label>
              <Input
                id="key"
                value={setting.key}
                disabled
                className="bg-muted"
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
                  const value = e.target.value as PlatformSettingUpdate['data_type'];
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
            <Button type="submit" disabled={updateMutation.isPending}>
              {updateMutation.isPending ? 'Updating...' : 'Update Setting'}
            </Button>
          </div>
        </form>
    </Dialog>
  );
};
