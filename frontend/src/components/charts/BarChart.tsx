/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * BarChart Component
 *
 * Reusable bar chart component using Recharts with theme support.
 */
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useTheme } from '@/lib/theme-context';

interface BarChartProps {
  data: Record<string, unknown>[];
  dataKey: string;
  xAxisKey?: string;
  bars?: {
    dataKey: string;
    name: string;
    color?: string;
  }[];
  height?: number;
  showLegend?: boolean;
  showGrid?: boolean;
}

export const BarChart = ({
  data,
  dataKey,
  xAxisKey = 'name',
  bars = [{ dataKey, name: 'Value' }],
  height = 300,
  showLegend = true,
  showGrid = true,
}: BarChartProps) => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const textColor = isDark ? 'hsl(210, 40%, 98%)' : 'hsl(222.2, 47.4%, 11.2%)';
  const gridColor = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';
  const tooltipBg = isDark ? 'hsl(222.2, 84%, 4.9%)' : 'hsl(0, 0%, 100%)';
  const tooltipBorder = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsBarChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
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
            borderRadius: '8px',
            color: textColor,
            padding: '8px 12px',
            boxShadow: isDark ? '0 4px 6px rgba(0, 0, 0, 0.3)' : '0 4px 6px rgba(0, 0, 0, 0.1)',
          }}
          itemStyle={{ color: textColor }}
        />
        {showLegend && (
          <Legend
            wrapperStyle={{ color: textColor }}
          />
        )}
        {bars.map((bar) => (
          <Bar
            key={bar.dataKey}
            dataKey={bar.dataKey}
            name={bar.name}
            fill={bar.color ?? `hsl(var(--primary))`}
            radius={[4, 4, 0, 0]}
          />
        ))}
      </RechartsBarChart>
    </ResponsiveContainer>
  );
};
