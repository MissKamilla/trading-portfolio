"use client";

import type { Position } from "@/lib/types";

interface PortfolioHeatmapProps {
  positions: Position[];
  totalValue: number;
}

interface HeatmapRect {
  ticker: string;
  x: number;
  y: number;
  width: number;
  height: number;
  allocationPercent: number;
  marketValue: number;
  pl: number;
  plPercent: number;
  color: string;
}

interface WeightedPosition extends Position {
  weight: number;
}

function formatCurrency(value: number): string {
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

function colorForPosition(position: Position): string {
  const intensity = Math.min(Math.abs(position.unrealized_pl_percent) / 8, 1);

  if (position.unrealized_pl >= 0) {
    const green = Math.floor(105 + intensity * 90);
    return `rgb(35, ${green}, 78)`;
  }

  const red = Math.floor(175 + intensity * 65);
  return `rgb(${red}, 68, 64)`;
}

function splitByWeight(items: WeightedPosition[]): [WeightedPosition[], WeightedPosition[]] {
  const half = items.reduce((sum, item) => sum + item.weight, 0) / 2;
  let running = 0;
  let splitIndex = 1;

  for (let i = 0; i < items.length - 1; i += 1) {
    running += items[i].weight;
    splitIndex = i + 1;
    if (running >= half) break;
  }

  return [items.slice(0, splitIndex), items.slice(splitIndex)];
}

function layoutTreemap(
  items: WeightedPosition[],
  x: number,
  y: number,
  width: number,
  height: number,
  totalValue: number,
): HeatmapRect[] {
  if (items.length === 0 || width <= 0 || height <= 0) return [];

  if (items.length === 1) {
    const item = items[0];
    return [{
      ticker: item.ticker,
      x,
      y,
      width,
      height,
      allocationPercent: totalValue > 0 ? (item.market_value / totalValue) * 100 : 0,
      marketValue: item.market_value,
      pl: item.unrealized_pl,
      plPercent: item.unrealized_pl_percent,
      color: colorForPosition(item),
    }];
  }

  const [leftItems, rightItems] = splitByWeight(items);
  const leftWeight = leftItems.reduce((sum, item) => sum + item.weight, 0);
  const totalWeight = items.reduce((sum, item) => sum + item.weight, 0);
  const ratio = totalWeight > 0 ? leftWeight / totalWeight : 0.5;

  if (width >= height) {
    const leftWidth = width * ratio;
    return [
      ...layoutTreemap(leftItems, x, y, leftWidth, height, totalValue),
      ...layoutTreemap(rightItems, x + leftWidth, y, width - leftWidth, height, totalValue),
    ];
  }

  const topHeight = height * ratio;
  return [
    ...layoutTreemap(leftItems, x, y, width, topHeight, totalValue),
    ...layoutTreemap(rightItems, x, y + topHeight, width, height - topHeight, totalValue),
  ];
}

function buildTreemap(positions: Position[], totalValue: number): HeatmapRect[] {
  const visiblePositions = positions
    .filter((position) => position.market_value > 0)
    .sort((a, b) => b.market_value - a.market_value);

  const investedValue = visiblePositions.reduce((sum, position) => sum + position.market_value, 0);
  if (visiblePositions.length === 0 || investedValue <= 0) return [];

  const weighted = visiblePositions.map((position) => ({
    ...position,
    weight: position.market_value / investedValue,
  }));

  return layoutTreemap(weighted, 0, 0, 100, 100, totalValue);
}

export default function PortfolioHeatmap({ positions, totalValue }: PortfolioHeatmapProps) {
  const rects = buildTreemap(positions, totalValue);
  const investedValue = positions.reduce((sum, position) => sum + Math.max(position.market_value, 0), 0);

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "#161b22", borderColor: "#21262d" }}
    >
      <div
        className="px-3 py-2 border-b shrink-0"
        style={{ borderColor: "#21262d" }}
      >
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#8b949e" }}>
            Portfolio Allocation
          </span>
          <span className="text-xs mono" style={{ color: "#484f58" }}>
            {positions.length}
          </span>
        </div>
      </div>

      {rects.length === 0 ? (
        <div className="flex items-center justify-center flex-1" style={{ color: "#484f58" }}>
          <p className="text-sm text-center px-4">No open positions</p>
        </div>
      ) : (
        <div className="flex flex-col flex-1 min-h-0 p-3 gap-3">
          <div className="grid grid-cols-2 gap-2 shrink-0">
            <div>
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "#484f58" }}>
                Invested
              </div>
              <div className="mono text-sm font-semibold" style={{ color: "#e6edf3" }}>
                {formatCurrency(investedValue)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider" style={{ color: "#484f58" }}>
                Cash
              </div>
              <div className="mono text-sm font-semibold" style={{ color: "#8b949e" }}>
                {totalValue > 0 ? `${Math.max(0, 100 - (investedValue / totalValue) * 100).toFixed(1)}%` : "0.0%"}
              </div>
            </div>
          </div>

          <div
            className="relative flex-1 min-h-[180px] overflow-hidden border"
            style={{ borderColor: "#21262d", background: "#0d1117", borderRadius: 6 }}
          >
            {rects.map((rect) => {
              const isWideEnough = rect.width >= 18;
              const isTallEnough = rect.height >= 14;
              const showDetails = isWideEnough && isTallEnough;
              const showTickerOnly = rect.width >= 10 && rect.height >= 8;
              const plColor = rect.pl >= 0 ? "#8ff0a4" : "#ffb4ad";

              return (
                <div
                  key={rect.ticker}
                  className="absolute overflow-hidden border"
                  title={`${rect.ticker}: ${rect.allocationPercent.toFixed(1)}%, ${formatCurrency(rect.marketValue)}, ${formatPercent(rect.plPercent)}`}
                  style={{
                    left: `${rect.x}%`,
                    top: `${rect.y}%`,
                    width: `${rect.width}%`,
                    height: `${rect.height}%`,
                    background: rect.color,
                    borderColor: "#0d1117",
                    borderRadius: 4,
                  }}
                >
                  {(showDetails || showTickerOnly) && (
                    <div className="flex h-full flex-col justify-between p-2">
                      <div className="min-w-0">
                        <div className="mono text-sm font-semibold truncate" style={{ color: "#ffffff" }}>
                          {rect.ticker}
                        </div>
                        {showDetails && (
                          <div className="mono text-xs" style={{ color: "rgba(255,255,255,0.76)" }}>
                            {rect.allocationPercent.toFixed(1)}%
                          </div>
                        )}
                      </div>

                      {showDetails && (
                        <div className="min-w-0">
                          <div className="mono text-xs truncate" style={{ color: "rgba(255,255,255,0.8)" }}>
                            {formatCurrency(rect.marketValue)}
                          </div>
                          <div className="mono text-xs font-semibold truncate" style={{ color: plColor }}>
                            {formatPercent(rect.plPercent)}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
