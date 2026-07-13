"use client";

import type { Position } from "@/lib/types";

interface PositionsTableProps {
  positions: Position[];
}

export default function PositionsTable({ positions }: PositionsTableProps) {
  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "#161b22", borderColor: "#21262d" }}
    >
      <div
        className="px-3 py-2 border-b shrink-0"
        style={{ borderColor: "#21262d" }}
      >
        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#8b949e" }}>
          Positions
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="flex items-center justify-center flex-1" style={{ color: "#484f58" }}>
          <p className="text-sm">No open positions</p>
        </div>
      ) : (
        <div className="flex-1 overflow-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr
                className="text-left"
                style={{ color: "#484f58", borderBottom: "1px solid #21262d" }}
              >
                {["Ticker", "Qty", "Avg Cost", "Price", "Mkt Value", "P&L ($)", "P&L (%)"].map((col) => (
                  <th key={col} className="px-3 py-1.5 font-medium uppercase tracking-wider">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.map((pos) => {
                const plColor = pos.unrealized_pl >= 0 ? "#3fb950" : "#f85149";
                const plSign = pos.unrealized_pl >= 0 ? "+" : "";
                return (
                  <tr
                    key={pos.ticker}
                    className="border-b transition-colors duration-150"
                    style={{ borderColor: "#21262d" }}
                  >
                    <td className="px-3 py-2 mono font-semibold" style={{ color: "#e6edf3" }}>
                      {pos.ticker}
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: "#e6edf3" }}>
                      {pos.quantity.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: "#8b949e" }}>
                      ${pos.avg_cost.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: "#e6edf3" }}>
                      ${pos.current_price.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 mono" style={{ color: "#8b949e" }}>
                      ${pos.market_value.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 mono font-medium" style={{ color: plColor }}>
                      {plSign}${pos.unrealized_pl.toFixed(2)}
                    </td>
                    <td className="px-3 py-2 mono font-medium" style={{ color: plColor }}>
                      {plSign}{pos.unrealized_pl_percent.toFixed(2)}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
