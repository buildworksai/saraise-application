/**
 * Email Campaign List Page - Email Marketing
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TableSkeleton, EmptyState, ErrorState } from '@/components/ui';
import { emailMarketingService } from '../services/email-marketing-service';
import type { EmailCampaign } from '../contracts';

const MODULE_PATH = '/email-marketing/campaigns';

export const EmailCampaignListPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: campaigns, isLoading, error, refetch } = useQuery({
    queryKey: ['email-campaigns'],
    queryFn: () => emailMarketingService.listCampaigns(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => emailMarketingService.deleteCampaign(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['email-campaigns'] });
      toast.success('Campaign deleted successfully');
    },
    onError: () => {
      toast.error('Failed to delete campaign. Please try again.');
    },
  });

  const handleDelete = async (id: string) => {
    if (window.confirm('Are you sure you want to delete this campaign?')) {
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
          message="Failed to load campaigns. Please check your connection and try again."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (!campaigns || campaigns.length === 0) {
    return (
      <div className="p-8">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-3xl font-bold text-foreground">Email Campaigns</h1>
          <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
            <Plus className="w-4 h-4 mr-2" />
            Create Campaign
          </Button>
        </div>
        <EmptyState
          icon={Plus}
          title="No campaigns yet"
          description="Create your first email campaign to get started."
          action={{
            label: 'Create Campaign',
            onClick: () => navigate(`${MODULE_PATH}/new`),
          }}
        />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Email Campaigns</h1>
        <Button onClick={() => navigate(`${MODULE_PATH}/new`)}>
          <Plus className="w-4 h-4 mr-2" />
          Create Campaign
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
                Subject
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Recipients
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {campaigns.map((campaign) => (
              <tr key={campaign.id} className="hover:bg-muted/50">
                <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                  {campaign.campaign_code}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{campaign.campaign_name}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm text-muted-foreground truncate max-w-[200px]">
                  {campaign.subject}
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{campaign.status}</td>
                <td className="px-6 py-4 whitespace-nowrap text-sm">{campaign.recipient_count}</td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <button
                    onClick={() => navigate(`${MODULE_PATH}/${campaign.id}`)}
                    className="text-primary hover:opacity-80 mr-4"
                  >
                    View
                  </button>
                  <button
                    onClick={() => void handleDelete(campaign.id)}
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
