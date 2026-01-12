/**
 * Opportunity Detail Page
 *
 * Displays opportunity details with close-won/close-lost actions.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2, CheckCircle, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { crmService } from '../services/crm-service';

export const OpportunityDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: opportunity, isLoading, error } = useQuery({
    queryKey: ['crm-opportunity', id],
    queryFn: () => (id ? crmService.getOpportunity(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const closeWonMutation = useMutation({
    mutationFn: () => (id ? crmService.closeOpportunityWon(id) : Promise.reject(new Error('No ID'))),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['crm-opportunity', id] });
      toast.success('Opportunity closed as won!');
    },
    onError: () => {
      toast.error('Failed to close opportunity. Please try again.');
    },
  });

  const closeLostMutation = useMutation({
    mutationFn: (reason: string) =>
      id ? crmService.closeOpportunityLost(id, reason) : Promise.reject(new Error('No ID')),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['crm-opportunity', id] });
      toast.success('Opportunity closed as lost.');
    },
    onError: () => {
      toast.error('Failed to close opportunity. Please try again.');
    },
  });

  const handleCloseWon = () => {
    if (window.confirm('Are you sure you want to mark this opportunity as won?')) {
      void closeWonMutation.mutate();
    }
  };

  const handleCloseLost = () => {
    const reason = window.prompt('Please provide a reason for closing as lost:');
    if (reason && id) {
      void closeLostMutation.mutate(reason);
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    );
  }

  if (error || !opportunity) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Opportunity not found</h2>
          <Button onClick={() => navigate('/crm/opportunities')}>Back to Opportunities</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('/crm/opportunities')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-3xl font-bold text-foreground">{opportunity.name}</h1>
        </div>
        <div className="flex gap-2">
          {opportunity.status === 'open' && (
            <>
              <Button variant="outline" onClick={handleCloseWon}>
                <CheckCircle className="w-4 h-4 mr-2" />
                Close Won
              </Button>
              <Button variant="outline" onClick={handleCloseLost}>
                <XCircle className="w-4 h-4 mr-2" />
                Close Lost
              </Button>
            </>
          )}
          <Button variant="outline" onClick={() => navigate(`/crm/opportunities/${opportunity.id}/edit`)}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Opportunity Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Amount</label>
                  <p className="text-sm font-medium">
                    {opportunity.currency} {parseFloat(opportunity.amount).toLocaleString()}
                  </p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Stage</label>
                  <div className="mt-1">
                    <StatusBadge
                      status={
                        opportunity.status === 'won'
                          ? 'active'
                          : opportunity.status === 'lost'
                            ? 'inactive'
                            : 'pending'
                      }
                    />
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Probability</label>
                  <p className="text-sm">{opportunity.probability}%</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Close Date</label>
                  <p className="text-sm">{new Date(opportunity.close_date).toLocaleDateString()}</p>
                </div>
              </div>
              {opportunity.description && (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Description</label>
                  <p className="text-sm mt-1">{opportunity.description}</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {opportunity.status === 'open' && (
                <>
                  <Button className="w-full" onClick={handleCloseWon}>
                    <CheckCircle className="w-4 h-4 mr-2" />
                    Close Won
                  </Button>
                  <Button variant="outline" className="w-full" onClick={handleCloseLost}>
                    <XCircle className="w-4 h-4 mr-2" />
                    Close Lost
                  </Button>
                </>
              )}
              <Button
                variant="outline"
                className="w-full"
                onClick={() =>
                  navigate(`/crm/activities/new?related_to_type=Opportunity&related_to_id=${opportunity.id}`)
                }
              >
                Log Activity
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
