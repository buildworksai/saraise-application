/**
 * Status Badge Component
 * 
 * Color-coded status badges for agents, executions, approvals, etc.
 */
import { clsx } from 'clsx';

export type StatusType = 
  | 'running' 
  | 'paused' 
  | 'completed' 
  | 'failed' 
  | 'pending' 
  | 'approved' 
  | 'rejected' 
  | 'active' 
  | 'inactive'
  | 'cancelled'
  | 'expired';

interface StatusBadgeProps {
  status: StatusType;
  className?: string;
}

const statusConfig: Record<StatusType, { label: string; className: string }> = {
  running: {
    label: 'Running',
    className: 'bg-primary/10 text-primary',
  },
  paused: {
    label: 'Paused',
    className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  },
  completed: {
    label: 'Completed',
    className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  },
  failed: {
    label: 'Failed',
    className: 'bg-destructive/10 text-destructive',
  },
  pending: {
    label: 'Pending',
    className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300',
  },
  approved: {
    label: 'Approved',
    className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  },
  rejected: {
    label: 'Rejected',
    className: 'bg-destructive/10 text-destructive',
  },
  active: {
    label: 'Active',
    className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  },
  inactive: {
    label: 'Inactive',
    className: 'bg-muted text-muted-foreground',
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-muted text-muted-foreground',
  },
  expired: {
    label: 'Expired',
    className: 'bg-orange-500/10 text-orange-700 dark:text-orange-300',
  },
};

export const StatusBadge = ({ status, className }: StatusBadgeProps) => {
  const config = statusConfig[status] || statusConfig.inactive;

  return (
    <span
      className={clsx(
        'px-2 py-1 text-xs rounded-full font-medium',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
};

