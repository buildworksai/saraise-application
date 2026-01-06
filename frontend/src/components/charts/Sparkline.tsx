/**
 * SPDX-License-Identifier: Apache-2.0
 *
 * Sparkline Component
 *
 * Mini inline chart for metric cards.
 */
import {
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';

interface SparklineProps {
  data: number[];
  color?: string;
  height?: number;
}

export const Sparkline = ({ data, color = 'hsl(var(--primary))', height = 40 }: SparklineProps) => {
  const chartData = data.map((value, index) => ({ value, index }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};

