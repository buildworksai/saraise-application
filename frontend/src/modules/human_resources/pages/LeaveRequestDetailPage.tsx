/* eslint-disable complexity -- request evidence and governed state actions form one atomic workflow. */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Check, Edit, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Dialog } from '@/components/ui/Dialog';
import { Textarea } from '@/components/ui/Textarea';
import { ROUTES, hrKeys } from '../contracts';
import { hrService, newIntentKey } from '../services/hr-service';
import {
  can, ConfirmAction, Detail, DetailGrid, GovernedError, PageShell, PageSkeleton,
  StatusChip, formatDate, formatInstant,
} from '../components/hr-ui';

type RequestAction = 'approve' | 'reject' | 'cancel';

export function LeaveRequestDetailPage() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [action, setAction] = useState<RequestAction | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const detail = useQuery({
    queryKey: hrKeys.leaveRequest(id),
    queryFn: () => hrService.getLeaveRequest(id),
    enabled: Boolean(id),
  });
  const transition = useMutation({
    mutationFn: async (next: RequestAction) => {
      const transition_key = newIntentKey();
      if (next === 'approve') return hrService.approveLeaveRequest(id, { transition_key });
      if (next === 'reject') {
        return hrService.rejectLeaveRequest(id, { transition_key, rejection_reason: rejectionReason });
      }
      return hrService.cancelLeaveRequest(id, { transition_key });
    },
    onSuccess: () => {
      setAction(null); setRejectionReason('');
      void client.invalidateQueries({ queryKey: hrKeys.all });
      toast.success('Leave request updated');
    },
  });
  if (detail.isLoading) return <PageSkeleton />;
  if (detail.error || !detail.data) {
    return <PageShell title="Leave request" description="Leave request detail.">
      <GovernedError error={detail.error} retry={() => void detail.refetch()} resource="Leave request" />
    </PageShell>;
  }
  const item = detail.data.data;
  const capabilities = detail.data.capabilities;
  const pending = item.status === 'pending';
  const cancellable = pending || (item.status === 'approved' && new Date(item.start_date) > new Date());
  return <PageShell
    title={`${item.employee_name} · ${item.leave_type} leave`}
    description={`${formatDate(item.start_date)} – ${formatDate(item.end_date)} · ${item.days_requested} calendar days`}
    back={() => navigate(ROUTES.LEAVE)}
    actions={<>
      {pending && can(capabilities, 'hr.leave_request:update') ? <Button variant="outline" onClick={() => navigate(ROUTES.LEAVE_REQUEST_EDIT(id))}><Edit className="mr-2 h-4 w-4" />Edit</Button> : null}
      {pending && can(capabilities, 'hr.leave_request:approve') ? <Button onClick={() => setAction('approve')}><Check className="mr-2 h-4 w-4" />Approve</Button> : null}
      {pending && can(capabilities, 'hr.leave_request:reject') ? <Button variant="danger" onClick={() => setAction('reject')}><X className="mr-2 h-4 w-4" />Reject</Button> : null}
      {cancellable && can(capabilities, 'hr.leave_request:cancel') ? <Button variant="outline" onClick={() => setAction('cancel')}>Cancel request</Button> : null}
    </>}
  >
    {!capabilities.length ? <p className="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">Action permissions are unavailable; privileged actions remain hidden for safety.</p> : null}
    <Card><CardHeader><div className="flex justify-between"><CardTitle>Request details</CardTitle><StatusChip status={item.status} /></div></CardHeader><CardContent><DetailGrid>
      <Detail label="Employee"><Link className="text-primary hover:underline" to={ROUTES.EMPLOYEE_DETAIL(item.employee)}>{item.employee_name} · {item.employee_number}</Link></Detail>
      <Detail label="Balance"><Link className="text-primary hover:underline" to={ROUTES.LEAVE_BALANCE_DETAIL(item.leave_balance)}>View allocation</Link></Detail>
      <Detail label="Days requested">{item.days_requested}</Detail>
      <Detail label="Reason">{item.reason || 'No reason supplied'}</Detail>
      <Detail label="Approved">{item.approved_at ? `${formatInstant(item.approved_at)} by ${item.approved_by}` : 'Not approved'}</Detail>
      <Detail label="Cancelled">{item.cancelled_at ? `${formatInstant(item.cancelled_at)} by ${item.cancelled_by}` : 'Not cancelled'}</Detail>
      {item.rejection_reason ? <Detail label="Rejection reason">{item.rejection_reason}</Detail> : null}
    </DetailGrid></CardContent></Card>
    <Card><CardHeader><CardTitle>State timeline</CardTitle></CardHeader><CardContent>
      {item.transition_history.length ? <ol className="border-l pl-5">{item.transition_history.map((record) => <li key={record.transition_key} className="mb-4"><strong className="capitalize">{record.command}</strong><p className="text-xs text-muted-foreground">{record.from_state} → {record.to_state} · {formatInstant(record.occurred_at)}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">The request is pending its first state transition.</p>}
    </CardContent></Card>
    {action === 'reject' ? <Dialog open onOpenChange={(open) => { if (!open && !transition.isPending) setAction(null); }} title="Reject leave request" description="A reason is required and will be visible in the request audit trail.">
      <label htmlFor="rejection-reason" className="mb-2 block text-sm font-medium">Rejection reason</label>
      <Textarea id="rejection-reason" required value={rejectionReason} onChange={(event) => setRejectionReason(event.target.value)} />
      <div className="mt-4 flex justify-end gap-3"><Button variant="outline" onClick={() => setAction(null)}>Keep pending</Button><Button variant="danger" disabled={!rejectionReason.trim() || transition.isPending} onClick={() => transition.mutate('reject')}>{transition.isPending ? 'Rejecting…' : 'Reject request'}</Button></div>
    </Dialog> : null}
    <ConfirmAction
      open={action === 'approve' || action === 'cancel'}
      onOpenChange={(open) => { if (!open) setAction(null); }}
      title={action === 'approve' ? 'Approve leave request?' : 'Cancel leave request?'}
      description={action === 'approve' ? 'Approval atomically converts reserved days into used leave.' : 'Cancellation releases reserved or future used days according to the request state.'}
      confirmLabel={action === 'approve' ? 'Approve request' : 'Cancel request'}
      danger={action === 'cancel'} pending={transition.isPending}
      onConfirm={() => { if (action) transition.mutate(action); }}
    />
    {transition.error ? <GovernedError error={transition.error} resource="Leave action" /> : null}
  </PageShell>;
}
