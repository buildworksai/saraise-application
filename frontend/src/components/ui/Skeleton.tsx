/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Skeleton Component
 *
 * Loading placeholder component with shimmer animation.
 */
import { cn } from '@/lib/utils';

type SkeletonProps = React.HTMLAttributes<HTMLDivElement>;

export const Skeleton = ({ className, ...props }: SkeletonProps) => {
  return (
    <div
      className={cn(
        'animate-pulse rounded-md bg-muted',
        className
      )}
      {...props}
    />
  );
};

/**
 * TableSkeleton Component
 *
 * Skeleton loader for data tables.
 */
interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

export const TableSkeleton = ({ rows = 5, columns = 6 }: TableSkeletonProps) => {
  return (
    <div className="space-y-4">
      {/* Header skeleton */}
      <div className="flex gap-4">
        <Skeleton className="h-10 flex-1" />
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-10 w-32" />
      </div>
      
      {/* Table skeleton */}
      <div className="border rounded-lg overflow-hidden">
        {/* Table header */}
        <div className="bg-muted border-b border-border">
          <div className="flex gap-4 p-4">
            {Array.from({ length: columns }).map((_, i) => (
              <Skeleton key={i} className="h-4 flex-1" />
            ))}
          </div>
        </div>
        
        {/* Table rows */}
        {Array.from({ length: rows }).map((_, rowIdx) => (
          <div key={rowIdx} className="flex gap-4 p-4 border-b border-border last:border-b-0">
            {Array.from({ length: columns }).map((_, colIdx) => (
              <Skeleton key={colIdx} className="h-4 flex-1" />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
};

/**
 * CardSkeleton Component
 *
 * Skeleton loader for dashboard cards.
 */
export const CardSkeleton = () => {
  return (
    <div className="rounded-lg border bg-card p-6">
      <Skeleton className="h-5 w-32 mb-4" />
      <Skeleton className="h-8 w-24 mb-2" />
      <Skeleton className="h-4 w-48" />
    </div>
  );
};

/**
 * ChartSkeleton Component
 *
 * Skeleton loader for charts.
 */
export const ChartSkeleton = ({ height = 300 }: { height?: number }) => {
  return (
    <div className="rounded-lg border bg-card p-6">
      <Skeleton className="h-5 w-48 mb-4" />
      <Skeleton className="h-4 w-32 mb-6" />
      <Skeleton style={{ height }} className="w-full" />
    </div>
  );
};
