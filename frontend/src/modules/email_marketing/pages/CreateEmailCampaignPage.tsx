/**
 * Create Email Campaign Page - Email Marketing
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { emailMarketingService } from '../services/email-marketing-service';
import type { EmailCampaignCreate } from '../contracts';

const MODULE_PATH = '/email-marketing/campaigns';

export const CreateEmailCampaignPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<EmailCampaignCreate>({
    campaign_code: '',
    campaign_name: '',
    subject: '',
    status: 'draft',
  });

  const createMutation = useMutation({
    mutationFn: (data: EmailCampaignCreate) => emailMarketingService.createCampaign(data),
    onSuccess: (campaign) => {
      void queryClient.invalidateQueries({ queryKey: ['email-campaigns'] });
      toast.success('Campaign created successfully');
      navigate(`${MODULE_PATH}/${campaign.id}`);
    },
    onError: () => {
      toast.error('Failed to create campaign. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.campaign_code.trim() ||
      !form.campaign_name.trim() ||
      !form.subject.trim() ||
      !form.status.trim()
    ) {
      toast.error('Code, name, subject, and status are required');
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
        <h1 className="text-3xl font-bold text-foreground">Create Email Campaign</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Campaign Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Campaign Code</label>
              <Input
                value={form.campaign_code}
                onChange={(e) => setForm({ ...form, campaign_code: e.target.value })}
                placeholder="e.g. CAMP001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Campaign Name</label>
              <Input
                value={form.campaign_name}
                onChange={(e) => setForm({ ...form, campaign_name: e.target.value })}
                placeholder="Campaign name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Subject</label>
              <Input
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                placeholder="Email subject line"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Status</label>
              <Input
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                placeholder="e.g. draft, scheduled"
                required
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Campaign'}
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
