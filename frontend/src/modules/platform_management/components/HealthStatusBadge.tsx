/**
 * HealthStatusBadge Component
 * 
 * Displays platform health status with appropriate styling.
 */
import { CheckCircle2, AlertTriangle, XCircle, Wrench } from 'lucide-react';

export type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'maintenance';

export interface HealthStatusBadgeProps {
  status: HealthStatus;
  uptime?: string;
  className?: string;
}

export const HealthStatusBadge = ({ status, uptime, className = '' }: HealthStatusBadgeProps) => {
  const statusConfig = {
    healthy: {
      icon: CheckCircle2,
      bgColor: 'bg-green-50 dark:bg-green-900/20',
      borderColor: 'border-green-200 dark:border-green-800',
      textColor: 'text-green-900 dark:text-green-100',
      iconColor: 'text-green-600 dark:text-green-400',
      label: 'Platform Status: Healthy',
    },
    degraded: {
      icon: AlertTriangle,
      bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
      borderColor: 'border-yellow-200 dark:border-yellow-800',
      textColor: 'text-yellow-900 dark:text-yellow-100',
      iconColor: 'text-yellow-600 dark:text-yellow-400',
      label: 'Platform Status: Degraded',
    },
    unhealthy: {
      icon: XCircle,
      bgColor: 'bg-red-50 dark:bg-red-900/20',
      borderColor: 'border-red-200 dark:border-red-800',
      textColor: 'text-red-900 dark:text-red-100',
      iconColor: 'text-red-600 dark:text-red-400',
      label: 'Platform Status: Unhealthy',
    },
    maintenance: {
      icon: Wrench,
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
      borderColor: 'border-blue-200 dark:border-blue-800',
      textColor: 'text-blue-900 dark:text-blue-100',
      iconColor: 'text-blue-600 dark:text-blue-400',
      label: 'Platform Status: Maintenance',
    },
  };

  const config = statusConfig[status];
  const Icon = config.icon;

  return (
    <div className={`p-4 ${config.bgColor} border ${config.borderColor} rounded-lg flex items-center gap-3 ${className}`}>
      <Icon className={`w-5 h-5 ${config.iconColor}`} />
      <div>
        <p className={`font-semibold ${config.textColor}`}>{config.label}</p>
        {uptime && (
          <p className={`text-sm ${config.textColor.replace('900', '700').replace('100', '300')}`}>
            All systems operational. Uptime: {uptime}
          </p>
        )}
      </div>
    </div>
  );
};

