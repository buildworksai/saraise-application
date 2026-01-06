/**
 * TenantStatusBadge Component
 * 
 * Displays tenant status with appropriate styling.
 */
import { CheckCircle2, Clock, AlertTriangle, XCircle, Archive } from 'lucide-react';

export type TenantStatus = 'trial' | 'active' | 'suspended' | 'cancelled' | 'archived';

export interface TenantStatusBadgeProps {
  status: TenantStatus;
  className?: string;
}

export const TenantStatusBadge = ({ status, className = '' }: TenantStatusBadgeProps) => {
  const statusConfig = {
    trial: {
      icon: Clock,
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
      borderColor: 'border-blue-200 dark:border-blue-800',
      textColor: 'text-blue-900 dark:text-blue-100',
      iconColor: 'text-blue-600 dark:text-blue-400',
      label: 'Trial',
    },
    active: {
      icon: CheckCircle2,
      bgColor: 'bg-green-50 dark:bg-green-900/20',
      borderColor: 'border-green-200 dark:border-green-800',
      textColor: 'text-green-900 dark:text-green-100',
      iconColor: 'text-green-600 dark:text-green-400',
      label: 'Active',
    },
    suspended: {
      icon: AlertTriangle,
      bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
      borderColor: 'border-yellow-200 dark:border-yellow-800',
      textColor: 'text-yellow-900 dark:text-yellow-100',
      iconColor: 'text-yellow-600 dark:text-yellow-400',
      label: 'Suspended',
    },
    cancelled: {
      icon: XCircle,
      bgColor: 'bg-red-50 dark:bg-red-900/20',
      borderColor: 'border-red-200 dark:border-red-800',
      textColor: 'text-red-900 dark:text-red-100',
      iconColor: 'text-red-600 dark:text-red-400',
      label: 'Cancelled',
    },
    archived: {
      icon: Archive,
      bgColor: 'bg-gray-50 dark:bg-gray-900/20',
      borderColor: 'border-gray-200 dark:border-gray-800',
      textColor: 'text-gray-900 dark:text-gray-100',
      iconColor: 'text-gray-600 dark:text-gray-400',
      label: 'Archived',
    },
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium ${config.bgColor} ${config.borderColor} border ${config.textColor} ${className}`}>
      <Icon className={`w-3.5 h-3.5 ${config.iconColor}`} />
      {config.label}
    </span>
  );
};

