/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * RingProgressIndicator Component
 *
 * Visual progress indicator for multi-stage processes (EUCORA-inspired design).
 * Adapted for SARAISE with compliance to design system.
 */
import { CheckCircle, Circle, XCircle, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface Ring {
  name: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  successRate?: number;
}

interface RingProgressIndicatorProps {
  rings: Ring[];
  className?: string;
}

export function RingProgressIndicator({ rings, className }: RingProgressIndicatorProps) {
  return (
    <div className={cn('flex flex-wrap items-center gap-4', className)}>
      {rings.map((ring, index) => (
        <div key={ring.name} className="flex items-center gap-2">
          {/* Ring status icon */}
          <div
            className={cn(
              'flex items-center justify-center w-12 h-12 rounded-full border-2 transition-all duration-300',
              ring.status === 'completed' && 'bg-green-500/20 border-green-500 dark:bg-green-400/20 dark:border-green-400',
              ring.status === 'in_progress' && 'bg-primary-main/20 border-primary-main animate-pulse',
              ring.status === 'failed' && 'bg-destructive/20 border-destructive',
              ring.status === 'pending' && 'bg-muted border-muted-foreground/30'
            )}
          >
            {ring.status === 'completed' && (
              <CheckCircle className="w-6 h-6 text-green-500 dark:text-green-400" />
            )}
            {ring.status === 'in_progress' && (
              <Clock className="w-6 h-6 text-primary-main" />
            )}
            {ring.status === 'failed' && (
              <XCircle className="w-6 h-6 text-destructive" />
            )}
            {ring.status === 'pending' && (
              <Circle className="w-6 h-6 text-muted-foreground/50" />
            )}
          </div>

          {/* Ring name and success rate */}
          <div className="flex flex-col">
            <span className="text-sm font-semibold">{ring.name}</span>
            {ring.successRate !== undefined && (
              <span className="text-xs text-muted-foreground">
                {ring.successRate.toFixed(1)}% success
              </span>
            )}
          </div>

          {/* Connector line to next ring */}
          {index < rings.length - 1 && (
            <div
              className={cn(
                'hidden md:block w-8 h-0.5 mx-2 rounded-full',
                ring.status === 'completed'
                  ? 'bg-green-500 dark:bg-green-400'
                  : 'bg-muted-foreground/20'
              )}
            />
          )}
        </div>
      ))}
    </div>
  );
}
