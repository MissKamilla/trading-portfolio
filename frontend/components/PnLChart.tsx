"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from "recharts";
import type { PortfolioSnapshot } from "@/lib/types";

interface PnLChartProps {
  history: PortfolioSnapshot[];
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatCurrency(value: number): string {
  return `$${value.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export default function PnLChart({ history }: PnLChartProps) {
  const data = history.map((s) => ({
    time: formatTime(s.recorded_at),
    iso: s.recorded_at,
    value: s.total_value,
  }));

  const startValue = data.length > 0 ? data[0].value : null;
  const lastValue = data.length > 0 ? data[data.length - 1].value : null;
  const isProfit = lastValue !== null && startValue !== null && lastValue >= startValue;
  const lineColor = isProfit ? "#3fb950" : "#f85149";

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "#161b22", borderColor: "#21262d" }}
    >
      <div
        className="flex items-center justify-between px-3 py-2 border-b shrink-0"
        style={{ borderColor: "#21262d" }}
      >
        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#8b949e" }}>
          P&amp;L Over Time
        </span>
        {startValue !== null && (
          <span className="text-xs mono" style={{ color: "#484f58" }}>
            Started at {formatCurrency(startValue)}
          </span>
        )}
      </div>

      <div className="flex-1 min-h-0 p-2">
        {data.length === 0 ? (
          <div className="flex items-center justify-center h-full" style={{ color: "#484f58" }}>
            <p className="text-sm">No history yet — portfolio snapshots are recorded every 30 seconds</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis
                dataKey="time"
                tick={{ fill: "#8b949e", fontSize: 10, fontFamily: "var(--font-geist-mono), monospace" }}
                axisLine={{ stroke: "#21262d" }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fill: "#8b949e", fontSize: 10, fontFamily: "var(--font-geist-mono), monospace" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={formatCurrency}
                width={70}
                domain={["auto", "auto"]}
              />
              {startValue !== null && (
                <ReferenceLine
                  y={startValue}
                  stroke="#30363d"
                  strokeDasharray="4 4"
                  label={{
                    value: "Start",
                    position: "insideTopRight",
                    fill: "#484f58",
                    fontSize: 9,
                  }}
                />
              )}
              <Tooltip
                contentStyle={{
                  background: "#161b22",
                  border: "1px solid #30363d",
                  borderRadius: 4,
                  color: "#e6edf3",
                  fontFamily: "var(--font-geist-mono), monospace",
                  fontSize: 12,
                }}
                labelStyle={{ color: "#8b949e" }}
                formatter={(value) => [formatCurrency(value as number), "Portfolio Value"]}
                labelFormatter={(_label, payload) => {
                  if (payload && payload[0]) {
                    return new Date(payload[0].payload?.iso ?? "").toLocaleString();
                  }
                  return _label;
                }}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke={lineColor}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: lineColor }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
