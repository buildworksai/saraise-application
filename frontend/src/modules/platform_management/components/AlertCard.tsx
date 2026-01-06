/**
 * AlertCard Component
 * 
 * Displays platform alerts with severity-based styling.
 */
import { AlertCircle, XCircle, Info } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import type { PlatformAlert } from '../services/platform-service';

export interface AlertCardProps {
  alert: PlatformAlert;
  onResolve?: (id: string) => void;
  className?: string;
}

export const AlertCard = ({ alert, onResolve, className = '' }: AlertCardProps) => {
  const severityConfig = {
    low: {
      icon: Info,
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
      borderColor: 'border-blue-200 dark:border-blue-800',
      textColor: 'text-blue-900 dark:text-blue-100',
      iconColor: 'text-blue-600 dark:text-blue-400',
    },
    medium: {
      icon: AlertCircle,
      bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
      borderColor: 'border-yellow-200 dark:border-yellow-800',
      textColor: 'text-yellow-900 dark:text-yellow-100',
      iconColor: 'text-yellow-600 dark:text-yellow-400',
    },
    high: {
      icon: AlertCircle,
      bgColor: 'bg-orange-50 dark:bg-orange-900/20',
      borderColor: 'border-orange-200 dark:border-orange-800',
      textColor: 'text-orange-900 dark:text-orange-100',
      iconColor: 'text-orange-600 dark:text-orange-400',
    },
    critical: {
      icon: XCircle,
      bgColor: 'bg-red-50 dark:bg-red-900/20',
      borderColor: 'border-red-200 dark:border-red-800',
      textColor: 'text-red-900 dark:text-red-100',
      iconColor: 'text-red-600 dark:text-red-400',
    },
  };

  const config = severityConfig[alert.severity] || severityConfig.medium;
  const Icon = config.icon;
  const isResolved = alert.status === 'resolved';

  return (
    <Card className={`p-4 ${config.bgColor} border ${config.borderColor} ${className}`}>
      <div className="flex items-start gap-3">
        <Icon className={`w-5 h-5 ${config.iconColor} mt-0.5 ${isResolved ? 'opacity-50' : ''}`} />
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <h4 className={`font-semibold ${config.textColor} ${isResolved ? 'line-through opacity-60' : ''}`}>
              {alert.title}
            </h4>
            {!isResolved && onResolve && (
              <button
                onClick={() => onResolve(alert.id!)}
                className="text-xs text-primary-main hover:text-primary-dark font-medium"
              >
                Resolve
              </button>
            )}
          </div>
          <p className={`text-sm ${config.textColor.replace('900', '700').replace('100', '300')} ${isResolved ? 'opacity-60' : ''}`}>
            {alert.description}
          </p>
          {alert.category && (
            <span className="inline-block mt-2 text-xs bg-muted px-2 py-1 rounded">
              {alert.category}
            </span>
          )}
          {alert.created_at && (
            <p className="text-xs text-muted-foreground mt-2">
              {new Date(alert.created_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
};
