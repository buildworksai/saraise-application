/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * AreaChart Component
 *
 * Reusable area chart component using Recharts with theme support.
 */
import {
  AreaChart as RechartsAreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useTheme } from '@/lib/theme-context';

interface AreaChartProps {
  data: Record<string, unknown>[];
  dataKey: string;
  xAxisKey?: string;
  areas?: {
    dataKey: string;
    name: string;
    color?: string;
  }[];
  height?: number;
  showLegend?: boolean;
  showGrid?: boolean;
}

export const AreaChart = ({
  data,
  dataKey,
  xAxisKey = 'timestamp',
  areas = [{ dataKey, name: 'Value' }],
  height = 300,
  showLegend = true,
  showGrid = true,
}: AreaChartProps) => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const textColor = isDark ? 'hsl(210, 40%, 98%)' : 'hsl(222.2, 47.4%, 11.2%)';
  const gridColor = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';
  const tooltipBg = isDark ? 'hsl(222.2, 84%, 4.9%)' : 'hsl(0, 0%, 100%)';
  const tooltipBorder = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsAreaChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        {showGrid && (
          <CartesianGrid strokeDasharray="3 3" stroke={gridColor} opacity={0.3} />
        )}
        <XAxis
          dataKey={xAxisKey}
          stroke={textColor}
          tick={{ fill: textColor }}
          style={{ fontSize: '12px' }}
        />
        <YAxis
          stroke={textColor}
          tick={{ fill: textColor }}
          style={{ fontSize: '12px' }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: tooltipBg,
            border: `1px solid ${tooltipBorder}`,
            borderRadius: '6px',
            color: textColor,
          }}
        />
        {showLegend && (
          <Legend
            wrapperStyle={{ color: textColor }}
          />
        )}
        {areas.map((area) => (
          <Area
            key={area.dataKey}
            type="monotone"
            dataKey={area.dataKey}
            name={area.name}
            stroke={area.color ?? `hsl(var(--primary))`}
            fill={area.color ?? `hsl(var(--primary))`}
            fillOpacity={0.3}
          />
        ))}
      </RechartsAreaChart>
    </ResponsiveContainer>
  );
};
