/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * LineChart Component
 *
 * Reusable line chart component using Recharts with theme support.
 */
import {
  LineChart as RechartsLineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useTheme } from '@/lib/theme-context';

interface LineChartProps {
  data: Record<string, unknown>[];
  dataKey: string;
  xAxisKey?: string;
  lines?: {
    dataKey: string;
    name: string;
    color?: string;
    strokeWidth?: number;
  }[];
  height?: number;
  showLegend?: boolean;
  showGrid?: boolean;
}

export const LineChart = ({
  data,
  dataKey,
  xAxisKey = 'timestamp',
  lines = [{ dataKey, name: 'Value' }],
  height = 300,
  showLegend = true,
  showGrid = true,
}: LineChartProps) => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const textColor = isDark ? 'hsl(210, 40%, 98%)' : 'hsl(222.2, 47.4%, 11.2%)';
  const gridColor = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';
  const tooltipBg = isDark ? 'hsl(222.2, 84%, 4.9%)' : 'hsl(0, 0%, 100%)';
  const tooltipBorder = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsLineChart data={data} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
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
            iconType="line"
          />
        )}
        {lines.map((line) => (
          <Line
            key={line.dataKey}
            type="monotone"
            dataKey={line.dataKey}
            name={line.name}
            stroke={line.color ?? `hsl(var(--primary))`}
            strokeWidth={line.strokeWidth ?? 2}
            dot={{ r: 3 }}
            activeDot={{ r: 5 }}
          />
        ))}
      </RechartsLineChart>
    </ResponsiveContainer>
  );
};
