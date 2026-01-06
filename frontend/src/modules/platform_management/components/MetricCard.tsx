/**
 * MetricCard Component
 * 
 * Reusable card component for displaying platform metrics.
 */
import { TrendingUp } from 'lucide-react';
import { Card } from '@/components/ui/Card';

export interface MetricCardProps {
  title: string;
  value: string | number;
  icon: React.ComponentType<{ className?: string }>;
  trend?: {
    value: string;
    isPositive: boolean;
  };
  description?: string;
  className?: string;
}

export const MetricCard = ({ 
  title, 
  value, 
  icon: Icon, 
  trend, 
  description,
  className = '',
}: MetricCardProps) => {
  return (
    <Card className={`p-6 hover:shadow-lg transition-shadow ${className}`}>
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-muted-foreground mb-1">{title}</p>
          <p className="text-3xl font-bold text-foreground mb-2">{value}</p>
          {trend && (
            <div className={`flex items-center gap-1 text-sm ${trend.isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
              <TrendingUp className={`w-4 h-4 ${trend.isPositive ? '' : 'rotate-180'}`} />
              <span>{trend.value}</span>
            </div>
          )}
          {description && (
            <p className="text-xs text-muted-foreground mt-2">{description}</p>
          )}
        </div>
        <div className="p-3 bg-primary-main/10 dark:bg-primary-main/20 rounded-lg">
          <Icon className="w-6 h-6 text-primary-main" />
        </div>
      </div>
    </Card>
  );
};

