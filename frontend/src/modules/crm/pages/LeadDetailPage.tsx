/**
 * Lead Detail Page
 *
 * Displays lead details with 360° view including activities and conversion options.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft, Edit, Trash2, TrendingUp, Mail, Phone, Building } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { crmService } from '../services/crm-service';
import type { Lead, Activity } from '../contracts';

export const LeadDetailPage = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: lead, isLoading, error } = useQuery({
    queryKey: ['crm-lead', id],
    queryFn: () => (id ? crmService.getLead(id) : Promise.reject(new Error('No ID'))),
    enabled: !!id,
  });

  const { data: activities } = useQuery({
    queryKey: ['crm-activities', id, 'Lead'],
    queryFn: () =>
      id
        ? crmService.listActivities({
            related_to_type: 'Lead',
            related_to_id: id,
          })
        : Promise.resolve([]),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: (leadId: string) => crmService.deleteLead(leadId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['crm-leads'] });
      toast.success('Lead deleted successfully');
      navigate('/crm/leads');
    },
    onError: () => {
      toast.error('Failed to delete lead. Please try again.');
    },
  });

  const convertMutation = useMutation({
    mutationFn: (data: { amount: string; close_date?: string }) =>
      id ? crmService.convertLead(id, data) : Promise.reject(new Error('No ID')),
    onSuccess: (opportunity) => {
      toast.success('Lead converted to opportunity');
      navigate(`/crm/opportunities/${opportunity.id}`);
    },
    onError: () => {
      toast.error('Failed to convert lead. Please try again.');
    },
  });

  const scoreMutation = useMutation({
    mutationFn: () => (id ? crmService.scoreLead(id) : Promise.reject(new Error('No ID'))),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['crm-lead', id] });
      toast.success('Lead scored successfully');
    },
    onError: () => {
      toast.error('Failed to score lead. Please try again.');
    },
  });

  const handleDelete = () => {
    if (id && window.confirm('Are you sure you want to delete this lead?')) {
      void deleteMutation.mutateAsync(id);
    }
  };

  const handleConvert = () => {
    const amount = window.prompt('Enter opportunity amount:');
    if (amount && id) {
      void convertMutation.mutateAsync({ amount });
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

  if (error || !lead) {
    return (
      <div className="p-8">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-foreground mb-4">Lead not found</h2>
          <Button onClick={() => navigate('/crm/leads')}>Back to Leads</Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" onClick={() => navigate('/crm/leads')}>
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back
          </Button>
          <h1 className="text-3xl font-bold text-foreground">
            {lead.first_name} {lead.last_name}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate(`/crm/leads/${lead.id}/edit`)}>
            <Edit className="w-4 h-4 mr-2" />
            Edit
          </Button>
          {lead.status !== 'converted' && (
            <Button onClick={handleConvert}>
              <TrendingUp className="w-4 h-4 mr-2" />
              Convert to Opportunity
            </Button>
          )}
          <Button variant="outline" onClick={() => void scoreMutation.mutate()}>
            Score Lead
          </Button>
          <Button variant="destructive" onClick={handleDelete}>
            <Trash2 className="w-4 h-4 mr-2" />
            Delete
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Details */}
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Lead Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Name</label>
                  <p className="text-sm font-medium">
                    {lead.first_name} {lead.last_name}
                  </p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Status</label>
                  <div className="mt-1">
                    <StatusBadge status={lead.status === 'converted' ? 'active' : 'inactive'} />
                  </div>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Email</label>
                  <p className="text-sm flex items-center gap-2">
                    <Mail className="w-4 h-4" />
                    {lead.email || '-'}
                  </p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Phone</label>
                  <p className="text-sm flex items-center gap-2">
                    <Phone className="w-4 h-4" />
                    {lead.phone || '-'}
                  </p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Company</label>
                  <p className="text-sm flex items-center gap-2">
                    <Building className="w-4 h-4" />
                    {lead.company || '-'}
                  </p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Title</label>
                  <p className="text-sm">{lead.title || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Source</label>
                  <p className="text-sm">{lead.source || '-'}</p>
                </div>
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Score</label>
                  <p className="text-sm font-medium">
                    {lead.score} ({lead.grade})
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Activities */}
          <Card>
            <CardHeader>
              <CardTitle>Activity Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              {activities && activities.length > 0 ? (
                <div className="space-y-4">
                  {activities.map((activity) => (
                    <div key={activity.id} className="border-l-2 border-border pl-4 py-2">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium">{activity.subject}</p>
                          <p className="text-xs text-muted-foreground">
                            {new Date(activity.created_at).toLocaleString()}
                          </p>
                        </div>
                        <StatusBadge
                          status={activity.completed ? 'active' : 'inactive'}
                          label={activity.activity_type}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No activities yet</p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <Button
                variant="outline"
                className="w-full"
                onClick={() => navigate(`/crm/activities/new?related_to_type=Lead&related_to_id=${lead.id}`)}
              >
                Log Activity
              </Button>
              {lead.status !== 'converted' && (
                <Button className="w-full" onClick={handleConvert}>
                  Convert to Opportunity
                </Button>
              )}
              <Button variant="outline" className="w-full" onClick={() => void scoreMutation.mutate()}>
                Recalculate Score
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Metadata</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm">
                <div>
                  <span className="text-muted-foreground">Created:</span>{' '}
                  <span>{new Date(lead.created_at).toLocaleDateString()}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Updated:</span>{' '}
                  <span>{new Date(lead.updated_at).toLocaleDateString()}</span>
                </div>
                {lead.converted_at && (
                  <div>
                    <span className="text-muted-foreground">Converted:</span>{' '}
                    <span>{new Date(lead.converted_at).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
