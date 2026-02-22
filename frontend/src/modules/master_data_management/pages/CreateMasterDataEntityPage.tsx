/**
 * Create Master Data Entity Page - Master Data Management
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { masterDataService } from '../services/master-data-service';
import type { MasterDataEntityCreate } from '../contracts';

const MODULE_PATH = '/master-data/entities';

export const CreateMasterDataEntityPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<MasterDataEntityCreate>({
    entity_type: '',
    entity_code: '',
    entity_name: '',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: MasterDataEntityCreate) => masterDataService.createEntity(data),
    onSuccess: (entity) => {
      void queryClient.invalidateQueries({ queryKey: ['master-data-entities'] });
      toast.success('Entity created successfully');
      navigate(`${MODULE_PATH}/${entity.id}`);
    },
    onError: () => {
      toast.error('Failed to create entity. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.entity_type.trim() ||
      !form.entity_code.trim() ||
      !form.entity_name.trim()
    ) {
      toast.error('Type, code, and name are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Master Data Entity</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Entity Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Entity Type</label>
              <Input
                value={form.entity_type}
                onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
                placeholder="e.g. customer, product"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Entity Code</label>
              <Input
                value={form.entity_code}
                onChange={(e) => setForm({ ...form, entity_code: e.target.value })}
                placeholder="e.g. ENT001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Entity Name</label>
              <Input
                value={form.entity_name}
                onChange={(e) => setForm({ ...form, entity_name: e.target.value })}
                placeholder="Entity name"
                required
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Entity'}
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
