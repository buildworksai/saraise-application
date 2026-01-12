/**
 * Approval Queue Page
 *
 * Displays pending approval requests with approve/reject actions.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aiAgentService } from '../services/ai-agent-service';
import { Check, X, AlertTriangle } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Textarea } from '@/components/ui/Textarea';
import { StatusBadge } from '@/components/ui/StatusBadge';

export const ApprovalQueuePage = () => {
  const queryClient = useQueryClient();
  const [rejectReason, setRejectReason] = useState<Record<string, string>>({});

  const { data: approvals, isLoading } = useQuery({
    queryKey: ['ai-agent-approvals', 'pending'],
    queryFn: () => aiAgentService.listApprovals('pending'),
  });

  const approveMutation = useMutation({
    mutationFn: (id: string) => aiAgentService.approveRequest(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agent-approvals'] });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      aiAgentService.rejectRequest(id, reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['ai-agent-approvals'] });
      setRejectReason({});
    },
  });

  const handleApprove = async (id: string) => {
    if (window.confirm('Are you sure you want to approve this request?')) {
      try {
        await approveMutation.mutateAsync(id);
      } catch {
        alert('Failed to approve request');
      }
    }
  };

  const handleReject = async (id: string) => {
    const existingReason = rejectReason[id];
    const reason = existingReason && existingReason.trim().length > 0
      ? existingReason
      : prompt('Enter rejection reason:');
    if (reason) {
      try {
        await rejectMutation.mutateAsync({ id, reason });
      } catch {
        alert('Failed to reject request');
      }
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="text-muted-foreground">Loading approvals...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground">Approval Queue</h1>
        <p className="mt-2 text-muted-foreground">
          Review and approve/reject pending approval requests
        </p>
      </div>

      {approvals?.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-muted-foreground">No pending approvals</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {approvals?.map((approval) => (
            <Card
              key={approval.id}
              className="p-6 border-l-4 border-amber-500/60"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-300" />
                    <h3 className="text-lg font-semibold text-foreground">
                      {approval.tool_name}
                    </h3>
                    <StatusBadge status="pending" />
                  </div>

                  <div className="space-y-1 text-sm text-muted-foreground">
                    <p>
                      <span className="font-medium">Agent Execution:</span>{' '}
                      {approval.agent_execution_id}
                    </p>
                    <p>
                      <span className="font-medium">Requested by:</span> {approval.requested_by}
                    </p>
                    <p>
                      <span className="font-medium">Requested for:</span> {approval.requested_for}
                    </p>
                    {approval.justification && (
                      <p>
                        <span className="font-medium">Justification:</span>{' '}
                        {approval.justification}
                      </p>
                    )}
                    <p>
                      <span className="font-medium">Requested at:</span>{' '}
                      {approval.requested_at ? new Date(approval.requested_at).toLocaleString() : 'N/A'}
                    </p>
                  </div>

                  {approval.id && rejectReason[approval.id] === undefined && (
                    <div className="mt-4">
                      <Textarea
                        placeholder="Rejection reason (optional)"
                        value={approval.id ? (rejectReason[approval.id] ?? '') : ''}
                        onChange={(e) =>
                          approval.id && setRejectReason({ ...rejectReason, [approval.id]: e.target.value })
                        }
                        className="text-sm"
                        rows={2}
                      />
                    </div>
                  )}
                </div>

                <div className="flex gap-2 ml-4">
                  <Button
                    onClick={() => {
                      if (approval.id) {
                        void handleApprove(approval.id);
                      }
                    }}
                    disabled={approveMutation.isPending || !approval.id}
                    variant="primary"
                  >
                    <Check className="w-4 h-4" />
                    Approve
                  </Button>
                  <Button
                    onClick={() => {
                      if (approval.id) {
                        void handleReject(approval.id);
                      }
                    }}
                    disabled={rejectMutation.isPending || !approval.id}
                    variant="danger"
                  >
                    <X className="w-4 h-4" />
                    Reject
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
