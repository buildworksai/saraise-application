/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * RiskScoreBadge Component
 *
 * Badge component for displaying risk scores with color-coded severity levels.
 * Adapted from EUCORA design for SARAISE compliance.
 */
import { cn } from '@/lib/utils';

interface RiskScoreBadgeProps {
  score: number | null;
  className?: string;
}

export function RiskScoreBadge({ score, className }: RiskScoreBadgeProps) {
  if (score === null) {
    return (
      <span
        className={cn(
          'px-2 py-1 text-xs rounded-full font-medium border',
          'bg-muted text-muted-foreground border-border',
          className
        )}
      >
        Not Scored
      </span>
    );
  }

  const getColorClass = () => {
    if (score <= 30) {
      return 'text-green-600 dark:text-green-400 border-green-500/20 dark:border-green-400/20 bg-green-500/10 dark:bg-green-400/10';
    }
    if (score <= 50) {
      return 'text-amber-600 dark:text-amber-400 border-amber-500/20 dark:border-amber-400/20 bg-amber-500/10 dark:bg-amber-400/10';
    }
    return 'bg-destructive/10 text-destructive border-destructive/20';
  };

  const getLabel = () => {
    if (score <= 30) return 'Low Risk';
    if (score <= 50) return 'Medium Risk';
    return 'High Risk';
  };

  return (
    <span
      className={cn(
        'px-2 py-1 text-xs rounded-full font-semibold border',
        getColorClass(),
        className
      )}
    >
      {score} - {getLabel()}
    </span>
  );
}
