/* eslint-disable max-lines-per-function, @typescript-eslint/no-unsafe-assignment -- Recharts is mocked as prop recorders so tests can assert wrapper contracts without jsdom layout. */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ThemeContext } from "@/lib/theme-context";
import { AreaChart } from "./AreaChart";
import { BarChart } from "./BarChart";
import { LineChart } from "./LineChart";
import { PieChart } from "./PieChart";
import { Sparkline } from "./Sparkline";

const rendered: Record<string, unknown[]> = {};

vi.mock("recharts", () => {
  const record =
    (name: string) =>
    ({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) => {
      rendered[name] = [...(rendered[name] ?? []), props];
      return <div data-testid={name}>{children}</div>;
    };

  return {
    Area: record("Area"),
    AreaChart: record("AreaChart"),
    Bar: record("Bar"),
    BarChart: record("BarChart"),
    CartesianGrid: record("CartesianGrid"),
    Cell: record("Cell"),
    Legend: record("Legend"),
    Line: record("Line"),
    LineChart: record("LineChart"),
    Pie: record("Pie"),
    PieChart: record("PieChart"),
    ResponsiveContainer: record("ResponsiveContainer"),
    Tooltip: record("Tooltip"),
    XAxis: record("XAxis"),
    YAxis: record("YAxis"),
  };
});

const data = [
  { timestamp: "2026-08-01", name: "North", revenue: 40, cost: 10 },
  { timestamp: "2026-08-02", name: "South", revenue: 65, cost: 30 },
];

const renderWithTheme = (node: ReactNode, theme: "light" | "dark" = "light") =>
  render(
    <ThemeContext.Provider value={{ theme, setTheme: vi.fn() }}>{node}</ThemeContext.Provider>
  );

describe("chart wrappers", () => {
  beforeEach(() => {
    for (const key of Object.keys(rendered)) {
      delete rendered[key];
    }
  });

  it("passes governed light-theme series and layout props to bar, line, area, and sparkline charts", () => {
    renderWithTheme(
      <>
        <BarChart
          data={data}
          dataKey="revenue"
          xAxisKey="name"
          height={220}
          showGrid={false}
          bars={[
            { dataKey: "revenue", name: "Revenue", color: "#0055aa" },
            { dataKey: "cost", name: "Cost" },
          ]}
        />
        <LineChart
          data={data}
          dataKey="revenue"
          showLegend={false}
          lines={[{ dataKey: "revenue", name: "Revenue", strokeWidth: 4 }]}
        />
        <AreaChart
          data={data}
          dataKey="cost"
          areas={[{ dataKey: "cost", name: "Cost", color: "#aa5500" }]}
        />
        <Sparkline data={[1, 3, 2]} color="#44aa66" height={28} />
      </>
    );

    expect(screen.getAllByTestId("ResponsiveContainer")).toHaveLength(4);
    expect(rendered.ResponsiveContainer).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ width: "100%", height: 220 }),
        expect.objectContaining({ width: "100%", height: 300 }),
        expect.objectContaining({ width: "100%", height: 28 }),
      ])
    );
    expect(rendered.CartesianGrid).toHaveLength(2);
    expect(rendered.XAxis).toEqual(
      expect.arrayContaining([expect.objectContaining({ dataKey: "name" })])
    );
    expect(rendered.Bar).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ dataKey: "revenue", name: "Revenue", fill: "#0055aa" }),
        expect.objectContaining({ dataKey: "cost", name: "Cost", fill: "hsl(var(--primary))" }),
      ])
    );
    expect(rendered.Line).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ dataKey: "revenue", name: "Revenue", strokeWidth: 4 }),
        expect.objectContaining({ dataKey: "value", stroke: "#44aa66", dot: false }),
      ])
    );
    expect(rendered.Area).toEqual(
      expect.arrayContaining([expect.objectContaining({ dataKey: "cost", fill: "#aa5500" })])
    );
    expect(rendered.Legend).toHaveLength(2);
  });

  it("renders dark themed pie and default series options with wrapped colors", () => {
    renderWithTheme(
      <>
        <PieChart
          data={[
            { name: "Open", value: 60 },
            { name: "Closed", value: 40 },
            { name: "Escalated", value: 10 },
          ]}
          innerRadius={24}
          colors={["#111111", "#222222"]}
        />
        <BarChart data={data} dataKey="revenue" />
        <LineChart data={data} dataKey="cost" />
        <AreaChart data={data} dataKey="cost" />
      </>,
      "dark"
    );

    expect(rendered.Pie).toEqual(
      expect.arrayContaining([expect.objectContaining({ innerRadius: 24, dataKey: "value" })])
    );
    expect(rendered.Cell).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ fill: "#111111" }),
        expect.objectContaining({ fill: "#222222" }),
        expect.objectContaining({ fill: "#111111" }),
      ])
    );
    expect(rendered.Bar).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ fill: "hsl(var(--primary))", name: "Value" }),
      ])
    );
    expect(rendered.Line).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ stroke: "hsl(var(--primary))", strokeWidth: 2 }),
      ])
    );
    expect(rendered.Area).toEqual(
      expect.arrayContaining([expect.objectContaining({ fillOpacity: 0.3, name: "Value" })])
    );
    expect(rendered.Tooltip).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          contentStyle: expect.objectContaining({ backgroundColor: "hsl(222.2, 84%, 4.9%)" }),
        }),
      ])
    );
  });
});
