"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import type { WatchlistItem, PriceUpdate } from "@/lib/types";
import * as api from "@/lib/api";

// ─── Sparkline ────────────────────────────────────────────────────────────

interface SparklineProps {
  history: PriceUpdate[];
  width?: number;
  height?: number;
}

function Sparkline({ history, width = 80, height = 28 }: SparklineProps) {
  const prices = history
    .map((p) => p.price)
    .filter((p): p is number => p !== null);

  if (prices.length < 2) {
    return (
      <svg width={width} height={height} className="opacity-40">
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="#484f58"
          strokeWidth={1}
          strokeDasharray="3,3"
        />
      </svg>
    );
  }

  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pad = 2;

  const points = prices.map((price, i) => {
    const x = (i / (prices.length - 1)) * width;
    const y = height - pad - ((price - min) / range) * (height - pad * 2);
    return `${x},${y}`;
  });

  const isUp = prices[prices.length - 1] >= prices[0];
  const color = isUp ? "#3fb950" : "#f85149";

  return (
    <svg width={width} height={height} overflow="visible">
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ─── Watchlist Row ─────────────────────────────────────────────────────────

interface WatchlistRowProps {
  item: WatchlistItem;
  history: PriceUpdate[];
  selected: boolean;
  onClick: () => void;
  onRemove: (ticker: string) => void;
  removing: boolean;
  flashClass?: string;
}

function WatchlistRow({
  item,
  history,
  selected,
  onClick,
  onRemove,
  removing,
  flashClass,
}: WatchlistRowProps) {
  const changeColor =
    item.change !== null && item.change > 0
      ? "text-[#3fb950]"
      : item.change !== null && item.change < 0
      ? "text-[#f85149]"
      : "text-[#8b949e]";

  const bgClass = selected ? "bg-[#1c2128]" : "";

  return (
    <div
      className={`grid grid-cols-[58px_76px_58px_minmax(46px,1fr)_28px] items-center gap-2 px-3 py-1.5 cursor-pointer border-b transition-colors duration-150 hover:bg-[#1c2128] ${bgClass} ${flashClass ?? ""}`}
      style={{ borderColor: "#21262d" }}
      onClick={onClick}
    >
      {/* Ticker */}
      <div className="mono text-sm font-semibold text-[#e6edf3] truncate">
        {item.ticker}
      </div>

      {/* Price */}
      <div className="mono text-sm text-[#e6edf3] text-right tabular-nums">
        {item.price !== null
          ? `$${item.price.toFixed(2)}`
          : item.price_status === "unavailable"
          ? "N/A"
          : "—"}
      </div>

      {/* Change */}
      <div className={`mono text-xs text-right tabular-nums ${changeColor}`}>
        {item.change_percent !== null
          ? `${item.change_percent >= 0 ? "+" : ""}${item.change_percent.toFixed(2)}%`
          : "—"}
      </div>

      {/* Sparkline */}
      <div className="min-w-0 flex justify-end overflow-hidden">
        <Sparkline history={history} width={56} />
      </div>

      {/* Remove button */}
      <button
        className="w-7 h-7 flex items-center justify-center text-[#8b949e] hover:text-[#ffffff] hover:bg-[#da3633] transition-colors rounded disabled:opacity-45 disabled:cursor-not-allowed"
        title={`Remove ${item.ticker}`}
        aria-label={`Remove ${item.ticker}`}
        disabled={removing}
        onClick={(e) => {
          e.stopPropagation();
          onRemove(item.ticker);
        }}
      >
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
          <line x1="1" y1="1" x2="9" y2="9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="9" y1="1" x2="1" y2="9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}

// ─── Watchlist ─────────────────────────────────────────────────────────────

interface WatchlistProps {
  items: WatchlistItem[];
  priceHistory: Map<string, PriceUpdate[]>;
  selectedTicker: string | null;
  onSelectTicker: (ticker: string) => void;
  onRefresh: () => void;
}

export default function Watchlist({
  items,
  priceHistory,
  selectedTicker,
  onSelectTicker,
  onRefresh,
}: WatchlistProps) {
  const [addInput, setAddInput] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [removingTicker, setRemovingTicker] = useState<string | null>(null);
  const [flashMap, setFlashMap] = useState<Record<string, string>>({});
  const prevPricesRef = useRef<Map<string, number | null>>(new Map());

  // Flash on price change
  const handleItemsChange = useCallback(
    (newItems: WatchlistItem[]) => {
      const flashes: Record<string, string> = {};
      for (const item of newItems) {
        const prev = prevPricesRef.current.get(item.ticker);
        if (prev !== undefined && item.price !== null && prev !== null) {
          if (item.price > prev) flashes[item.ticker] = "flash-up";
          else if (item.price < prev) flashes[item.ticker] = "flash-down";
        }
        prevPricesRef.current.set(item.ticker, item.price);
      }
      if (Object.keys(flashes).length > 0) {
        setFlashMap((prev) => ({ ...prev, ...flashes }));
        setTimeout(() => {
          setFlashMap((prev) => {
            const next = { ...prev };
            Object.keys(flashes).forEach((t) => delete next[t]);
            return next;
          });
        }, 520);
      }
    },
    []
  );

  useEffect(() => {
    const timeout = setTimeout(() => handleItemsChange(items), 0);
    return () => clearTimeout(timeout);
  }, [items, handleItemsChange]);

  const handleAdd = async () => {
    if (adding) return;
    const ticker = addInput.trim().toUpperCase();
    if (!ticker) return;
    setAddError(null);
    setAdding(true);
    try {
      await api.addToWatchlist(ticker);
      setAddInput("");
      onRefresh();
    } catch (e: unknown) {
      const msg =
        (e as { error?: { message?: string } })?.error?.message ??
        "Failed to add ticker.";
      setAddError(msg);
    } finally {
      setAdding(false);
    }
  };

  const handleRemove = async (ticker: string) => {
    if (removingTicker) return;
    setRemoveError(null);
    setRemovingTicker(ticker);
    try {
      await api.removeFromWatchlist(ticker);
      onRefresh();
    } catch (e: unknown) {
      const msg =
        (e as { error?: { message?: string } })?.error?.message ??
        `Failed to remove ${ticker}.`;
      setRemoveError(msg);
    } finally {
      setRemovingTicker(null);
    }
  };

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "#161b22", borderColor: "#21262d" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2 border-b shrink-0"
        style={{ borderColor: "#21262d" }}
      >
        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#8b949e" }}>
          Watchlist
        </span>
        <span className="text-xs mono" style={{ color: "#484f58" }}>
          {items.length} / 30
        </span>
      </div>

      {/* Column Headers */}
      <div
        className="flex items-center gap-2 px-3 py-1 border-b text-xs shrink-0"
        style={{ borderColor: "#21262d", color: "#484f58" }}
      >
        <div className="w-14 shrink-0">Symbol</div>
        <div className="w-20 text-right shrink-0">Price</div>
        <div className="w-16 text-right shrink-0">Chg%</div>
        <div className="flex-1" />
      </div>

      {/* Rows */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {items.map((item) => (
          <WatchlistRow
            key={item.ticker}
            item={item}
            history={priceHistory.get(item.ticker) ?? []}
            selected={item.ticker === selectedTicker}
            onClick={() => onSelectTicker(item.ticker)}
            onRemove={handleRemove}
            removing={removingTicker === item.ticker}
            flashClass={flashMap[item.ticker]}
          />
        ))}
        {items.length === 0 && (
          <div className="flex items-center justify-center h-24 text-sm" style={{ color: "#484f58" }}>
            No tickers in watchlist
          </div>
        )}
        {removeError && (
          <div className="px-3 py-2 text-xs" style={{ color: "#f85149" }}>
            {removeError}
          </div>
        )}
      </div>

      {/* Add Ticker */}
      <div
        className="px-3 py-2 border-t shrink-0"
        style={{ borderColor: "#21262d" }}
      >
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void handleAdd();
          }}
        >
          <input
            className="flex-1 px-2 py-1 text-sm bg-[#0d1117] border rounded text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff] transition-colors"
            style={{ borderColor: "#30363d" }}
            placeholder="Add ticker..."
            value={addInput}
            onChange={(e) => setAddInput(e.target.value.toUpperCase())}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="characters"
            spellCheck={false}
            maxLength={10}
          />
          <button
            type="submit"
            className="w-8 h-8 flex items-center justify-center border text-lg font-semibold transition-colors disabled:opacity-45 disabled:cursor-not-allowed hover:bg-[#2ea043] focus:outline-none focus:border-[#58a6ff]"
            style={{
              background: "#238636",
              borderColor: "#2ea043",
              color: "#ffffff",
              borderRadius: 6,
            }}
            disabled={adding || !addInput.trim()}
            title="Add ticker"
            aria-label="Add ticker"
          >
            {adding ? "..." : "+"}
          </button>
        </form>
        {addError && (
          <div className="mt-1 text-xs" style={{ color: "#f85149" }}>
            {addError}
          </div>
        )}
      </div>
    </div>
  );
}
