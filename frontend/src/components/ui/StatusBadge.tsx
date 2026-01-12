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
    className: 'bg-primary/10 text-primary border-primary/20',
  },
  paused: {
    label: 'Paused',
    className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 dark:border-amber-400/20',
  },
  completed: {
    label: 'Completed',
    className: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20 dark:border-green-400/20',
  },
  failed: {
    label: 'Failed',
    className: 'bg-destructive/10 text-destructive border-destructive/20',
  },
  pending: {
    label: 'Pending',
    className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 dark:border-amber-400/20',
  },
  approved: {
    label: 'Approved',
    className: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20 dark:border-green-400/20',
  },
  rejected: {
    label: 'Rejected',
    className: 'bg-destructive/10 text-destructive border-destructive/20',
  },
  active: {
    label: 'Active',
    className: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/20 dark:border-green-400/20',
  },
  inactive: {
    label: 'Inactive',
    className: 'bg-muted text-muted-foreground border-border',
  },
  cancelled: {
    label: 'Cancelled',
    className: 'bg-muted text-muted-foreground border-border',
  },
  expired: {
    label: 'Expired',
    className: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20 dark:border-orange-400/20',
  },
};

export const StatusBadge = ({ status, className }: StatusBadgeProps) => {
  const config = statusConfig[status] || statusConfig.inactive;

  return (
    <span
      className={clsx(
        'px-2 py-1 text-xs rounded-full font-medium border',
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  );
};
