"use client";

import type { ConnectionStatus } from "@/lib/types";

interface HeaderProps {
  totalValue: number | null;
  cashBalance: number | null;
  connectionStatus: ConnectionStatus;
}

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connected: "Connected",
  reconnecting: "Reconnecting...",
  disconnected: "Disconnected",
};

export default function Header({ totalValue, cashBalance, connectionStatus }: HeaderProps) {
  const statusColor: Record<ConnectionStatus, string> = {
    connected: "bg-[#3fb950]",
    reconnecting: "bg-[#d29922]",
    disconnected: "bg-[#f85149]",
  };

  return (
    <header
      className="flex items-center justify-between px-4 py-2 border-b"
      style={{
        background: "#161b22",
        borderColor: "#21262d",
      }}
    >
      {/* Left: Logo */}
      <div className="flex items-center gap-3">
        <span className="text-[#58a6ff] font-semibold text-lg tracking-tight">
          FinAlly
        </span>
        <span
          className="text-xs px-2 py-0.5 rounded"
          style={{ background: "#1c2128", color: "#8b949e" }}
        >
          AI Trading
        </span>
      </div>

      {/* Center: Portfolio Value */}
      <div className="flex items-center gap-8">
        <div className="text-center">
          <div className="text-xs" style={{ color: "#8b949e" }}>
            Portfolio Value
          </div>
          <div
            className="mono text-xl font-semibold"
            style={{ color: "#e6edf3" }}
          >
            {totalValue !== null
              ? `$${totalValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "—"}
          </div>
        </div>

        <div
          className="w-px"
          style={{ background: "#21262d", height: "32px" }}
        />

        <div className="text-center">
          <div className="text-xs" style={{ color: "#8b949e" }}>
            Cash Available
          </div>
          <div
            className="mono text-xl font-semibold"
            style={{ color: "#e6edf3" }}
          >
            {cashBalance !== null
              ? `$${cashBalance.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "—"}
          </div>
        </div>
      </div>

      {/* Right: Connection Status */}
      <div className="flex items-center gap-2">
        <div
          className={`w-2 h-2 rounded-full ${statusColor[connectionStatus]} transition-colors duration-300`}
          title={STATUS_LABELS[connectionStatus]}
        />
        <span className="text-xs" style={{ color: "#8b949e" }}>
          {STATUS_LABELS[connectionStatus]}
        </span>
      </div>
    </header>
  );
}
