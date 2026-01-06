/**
 * TimeRangeSelector Component
 * 
 * Dropdown selector for time range (7d, 30d, 90d, etc.)
 */
import { Select } from '@/components/ui/Select';

export type TimeRange = '7d' | '30d' | '90d' | '1y';

export interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (value: TimeRange) => void;
  label?: string;
  className?: string;
}

const timeRangeOptions: { value: TimeRange; label: string }[] = [
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: '90d', label: 'Last 90 days' },
  { value: '1y', label: 'Last year' },
];

export const TimeRangeSelector = ({ 
  value, 
  onChange, 
  label = 'Time Range',
  className = '',
}: TimeRangeSelectorProps) => {
  return (
    <div className={className}>
      <Select
        value={value}
        onChange={(e) => onChange(e.target.value as TimeRange)}
        options={timeRangeOptions}
        label={label}
        className="w-full"
      />
    </div>
  );
};
