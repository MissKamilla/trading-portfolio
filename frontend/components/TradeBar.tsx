"use client";

import { useState } from "react";
import type { ApiError } from "@/lib/types";
import * as api from "@/lib/api";

interface TradeBarProps {
  selectedTicker: string | null;
  cashBalance: number | null;
  onTradeExecuted: () => void;
}

export default function TradeBar({ selectedTicker, cashBalance, onTradeExecuted }: TradeBarProps) {
  const [ticker, setTicker] = useState(selectedTicker ?? "");
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (side: "buy" | "sell") => {
    const t = ticker.trim().toUpperCase();
    const q = parseFloat(quantity);
    if (!t) { setError("Enter a ticker symbol."); return; }
    if (isNaN(q) || q <= 0) { setError("Enter a positive quantity."); return; }

    setError(null);
    setSuccess(null);
    setLoading(true);

    try {
      const res = await api.executeTrade(t, side, q);
      setSuccess(
        `${side === "buy" ? "Bought" : "Sold"} ${res.trade.quantity} ${res.trade.ticker} at $${res.trade.price.toFixed(2)} — Cash: $${res.cash_balance.toFixed(2)}`
      );
      setQuantity("");
      onTradeExecuted();
    } catch (e: unknown) {
      const apiErr = e as ApiError;
      setError(apiErr?.error?.message ?? "Trade failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="flex flex-col gap-2 px-4 py-3 border-t"
      style={{ background: "#161b22", borderColor: "#21262d" }}
    >
      <div className="flex items-center gap-2">
        {/* Ticker input */}
        <div className="flex flex-col">
          <label className="text-xs mb-0.5" style={{ color: "#484f58" }}>Ticker</label>
          <input
            className="w-20 px-2 py-1 text-sm mono bg-[#0d1117] border rounded text-[#e6edf3] focus:outline-none focus:border-[#58a6ff] transition-colors"
            style={{ borderColor: "#30363d" }}
            placeholder="AAPL"
            value={ticker}
            onChange={(e) => setTicker(e.target.value.toUpperCase())}
            maxLength={10}
          />
        </div>

        {/* Quantity input */}
        <div className="flex flex-col">
          <label className="text-xs mb-0.5" style={{ color: "#484f58" }}>Qty</label>
          <input
            className="w-24 px-2 py-1 text-sm mono bg-[#0d1117] border rounded text-[#e6edf3] focus:outline-none focus:border-[#58a6ff] transition-colors"
            style={{ borderColor: "#30363d" }}
            placeholder="0"
            type="number"
            min="0"
            step="any"
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSubmit("buy")}
          />
        </div>

        {/* Cash balance */}
        <div className="flex flex-col justify-end">
          <span className="text-xs mb-0.5" style={{ color: "#484f58" }}>Cash</span>
          <span className="mono text-sm" style={{ color: "#8b949e" }}>
            {cashBalance !== null
              ? `$${cashBalance.toLocaleString("en-US", { minimumFractionDigits: 2 })}`
              : "—"}
          </span>
        </div>

        <div className="flex-1" />

        {/* Buy / Sell buttons */}
        <div className="flex flex-col justify-end gap-1">
          <button
            className="px-5 py-1.5 text-sm font-semibold rounded transition-colors disabled:opacity-40"
            style={{ background: "#238636", color: "#ffffff" }}
            onClick={() => handleSubmit("buy")}
            disabled={loading}
          >
            Buy
          </button>
          <button
            className="px-5 py-1.5 text-sm font-semibold rounded transition-colors disabled:opacity-40"
            style={{ background: "#b62324", color: "#ffffff" }}
            onClick={() => handleSubmit("sell")}
            disabled={loading}
          >
            Sell
          </button>
        </div>
      </div>

      {/* Messages */}
      {error && (
        <div className="text-xs px-2 py-1 rounded" style={{ background: "rgba(248,81,73,0.1)", color: "#f85149" }}>
          {error}
        </div>
      )}
      {success && (
        <div className="text-xs px-2 py-1 rounded" style={{ background: "rgba(63,185,80,0.1)", color: "#3fb950" }}>
          {success}
        </div>
      )}
    </div>
  );
}
