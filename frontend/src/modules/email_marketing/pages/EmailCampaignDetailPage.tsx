/**
 * Email Campaign Detail Page - Email Marketing
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { emailMarketingService } from '../services/email-marketing-service';

const MODULE_PATH = '/email-marketing/campaigns';

export const EmailCampaignDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: campaign, isLoading, error } = useQuery({
    queryKey: ['email-campaign', id],
    queryFn: () =>
      id ? emailMarketingService.getCampaign(id) : Promise.reject(new Error('No ID')),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (campaignId: string) => emailMarketingService.deleteCampaign(campaignId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['email-campaigns'] });
      toast.success('Campaign deleted successfully');
      navigate(MODULE_PATH);
    },
    onError: () => {
      toast.error('Failed to delete campaign. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this campaign?')) {
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

  if (error || !campaign) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Campaign not found</h2>
          <Button onClick={() => navigate(MODULE_PATH)}>Back to Campaigns</Button>
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
            {campaign.campaign_code} - {campaign.campaign_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`${MODULE_PATH}/${campaign.id}/edit`)}>
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
          <CardTitle>Campaign Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Code</label>
              <p className="text-sm font-medium">{campaign.campaign_code}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Name</label>
              <p className="text-sm font-medium">{campaign.campaign_name}</p>
            </div>
            <div className="col-span-2">
              <label className="text-sm font-medium text-muted-foreground">Subject</label>
              <p className="text-sm">{campaign.subject}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Status</label>
              <p className="text-sm">{campaign.status}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Recipients</label>
              <p className="text-sm">{campaign.recipient_count}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Opened</label>
              <p className="text-sm">{campaign.opened_count}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Clicked</label>
              <p className="text-sm">{campaign.clicked_count}</p>
            </div>
            {campaign.sent_at && (
              <div>
                <label className="text-sm font-medium text-muted-foreground">Sent At</label>
                <p className="text-sm">{new Date(campaign.sent_at).toLocaleString()}</p>
              </div>
            )}
          </div>
          <div className="pt-4 border-t border-border text-sm text-muted-foreground">
            <span>Created: {new Date(campaign.created_at).toLocaleDateString()}</span>
            <span className="ml-4">Updated: {new Date(campaign.updated_at).toLocaleDateString()}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
