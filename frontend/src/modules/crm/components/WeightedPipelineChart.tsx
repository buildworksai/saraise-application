/**
 * Weighted Pipeline Chart Component
 *
 * Visualizes pipeline value by stage using recharts.
 */
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { Opportunity } from '../contracts';

interface WeightedPipelineChartProps {
  opportunities: Opportunity[];
}

export const WeightedPipelineChart = ({ opportunities }: WeightedPipelineChartProps) => {
  // Calculate pipeline value by stage
  const stageData = opportunities.reduce(
    (acc, opp) => {
      const stage = opp.stage;
      if (!acc[stage]) {
        acc[stage] = {
          stage: stage.replace('_', ' '),
          totalValue: 0,
          weightedValue: 0,
          count: 0,
        };
      }
      const amount = parseFloat(opp.amount);
      const probability = opp.probability / 100;
      acc[stage].totalValue += amount;
      acc[stage].weightedValue += amount * probability;
      acc[stage].count += 1;
      return acc;
    },
    {} as Record<
      string,
      { stage: string; totalValue: number; weightedValue: number; count: number }
    >
  );

  const chartData = Object.values(stageData).map((data) => ({
    ...data,
    totalValue: Math.round(data.totalValue),
    weightedValue: Math.round(data.weightedValue),
  }));

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        No pipeline data available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis
          dataKey="stage"
          angle={-45}
          textAnchor="end"
          height={80}
          tick={{ fontSize: 12 }}
        />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          formatter={(value: number) => `$${value.toLocaleString()}`}
          labelStyle={{ color: '#000' }}
        />
        <Legend />
        <Bar dataKey="totalValue" fill="#8884d8" name="Total Pipeline" />
        <Bar dataKey="weightedValue" fill="#82ca9d" name="Weighted Pipeline" />
      </BarChart>
    </ResponsiveContainer>
  );
};
