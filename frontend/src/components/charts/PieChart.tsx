/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * PieChart Component
 *
 * Reusable pie/donut chart component using Recharts with theme support.
 */
import {
  PieChart as RechartsPieChart,
  Pie,
  Cell,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { useTheme } from '@/lib/theme-context';

interface PieChartProps {
  data: { name: string; value: number }[];
  height?: number;
  innerRadius?: number; // 0 = pie, >0 = donut
  showLegend?: boolean;
  colors?: string[];
}

const DEFAULT_COLORS = [
  'hsl(var(--primary))',
  'hsl(var(--secondary))',
  'hsl(var(--accent))',
  'hsl(var(--muted))',
  'hsl(var(--destructive))',
];

export const PieChart = ({
  data,
  height = 300,
  innerRadius = 0,
  showLegend = true,
  colors = DEFAULT_COLORS,
}: PieChartProps) => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const textColor = isDark ? 'hsl(210, 40%, 98%)' : 'hsl(222.2, 47.4%, 11.2%)';
  const tooltipBg = isDark ? 'hsl(222.2, 84%, 4.9%)' : 'hsl(0, 0%, 100%)';
  const tooltipBorder = isDark ? 'hsl(217.2, 32.6%, 17.5%)' : 'hsl(214.3, 31.8%, 91.4%)';

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RechartsPieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          labelLine={false}
          label={({ name, percent }) => `${name}: ${((percent ?? 0) * 100).toFixed(0)}%`}
          outerRadius={80}
          innerRadius={innerRadius}
          fill="hsl(var(--primary))"
          dataKey="value"
        >
          {data.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={colors[index % colors.length]} />
          ))}
        </Pie>
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
      </RechartsPieChart>
    </ResponsiveContainer>
  );
};
