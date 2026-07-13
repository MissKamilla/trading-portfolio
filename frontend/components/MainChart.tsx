"use client";

import { useEffect, useRef } from "react";
import type { PriceUpdate } from "@/lib/types";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickSeries,
  LineSeries,
  CandlestickData,
  LineData,
  Time,
} from "lightweight-charts";

interface MainChartProps {
  ticker: string | null;
  priceHistory: Map<string, PriceUpdate[]>;
  currentPrice: number | null;
  direction: "up" | "down" | "flat" | null;
}

function toUnixSeconds(timestamp: number | string): number {
  if (typeof timestamp === "number") {
    return timestamp > 10_000_000_000 ? Math.floor(timestamp / 1000) : Math.floor(timestamp);
  }
  return Math.floor(new Date(timestamp).getTime() / 1000);
}

function bucketTimestamp(unixSeconds: number, bucketSizeSeconds = 5): number {
  return Math.floor(unixSeconds / bucketSizeSeconds) * bucketSizeSeconds;
}

export default function MainChart({ ticker, priceHistory, currentPrice, direction }: MainChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);

  // Init chart once
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#0d1117" },
        textColor: "#8b949e",
        fontFamily: "var(--font-mono), monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#21262d" },
        horzLines: { color: "#21262d" },
      },
      crosshair: {
        mode: 1,
        vertLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
        horzLine: { color: "#30363d", labelBackgroundColor: "#161b22" },
      },
      rightPriceScale: {
        borderColor: "#21262d",
        textColor: "#8b949e",
      },
      timeScale: {
        borderColor: "#21262d",
        timeVisible: true,
        secondsVisible: true,
      },
      handleScroll: true,
      handleScale: true,
    });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#3fb950",
      downColor: "#f85149",
      borderUpColor: "#3fb950",
      borderDownColor: "#f85149",
      wickUpColor: "#3fb950",
      wickDownColor: "#f85149",
    });

    const line = chart.addSeries(LineSeries, {
      color: "#58a6ff",
      lineWidth: 2,
      priceLineVisible: true,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candle;
    lineSeriesRef.current = line;

    // Resize observer
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width: Math.floor(width), height: Math.floor(height) });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      lineSeriesRef.current = null;
    };
  }, []);

  // Update data when history or ticker changes
  useEffect(() => {
    if (!candleSeriesRef.current || !lineSeriesRef.current) return;

    if (!ticker) {
      candleSeriesRef.current.setData([]);
      lineSeriesRef.current.setData([]);
      return;
    }

    const history = priceHistory.get(ticker) ?? [];
    if (history.length === 0) {
      candleSeriesRef.current.setData([]);
      lineSeriesRef.current.setData([]);
      return;
    }

    const candleMap = new Map<number, { o: number; h: number; l: number; c: number; t: number }>();
    const lineByTime = new Map<number, number>();

    for (const update of history) {
      if (update.price === null) continue;
      const unixSeconds = toUnixSeconds(update.timestamp);
      if (!Number.isFinite(unixSeconds)) continue;

      lineByTime.set(unixSeconds, update.price);

      const bucket = bucketTimestamp(unixSeconds);

      if (!candleMap.has(bucket)) {
        candleMap.set(bucket, { o: update.price, h: update.price, l: update.price, c: update.price, t: bucket });
      } else {
        const candle = candleMap.get(bucket)!;
        candle.h = Math.max(candle.h, update.price);
        candle.l = Math.min(candle.l, update.price);
        candle.c = update.price;
      }
    }

    const sortedCandles = Array.from(candleMap.values()).sort((a, b) => a.t - b.t);

    const candleData: CandlestickData<Time>[] = sortedCandles.map((candle) => ({
      time: candle.t as Time,
      open: candle.o,
      high: candle.h,
      low: candle.l,
      close: candle.c,
    }));

    const lineData: LineData<Time>[] = Array.from(lineByTime.entries())
      .sort(([a], [b]) => a - b)
      .map(([time, value]) => ({
        time: time as Time,
        value,
      }));

    candleSeriesRef.current.setData(candleData);
    lineSeriesRef.current.setData(lineData);
    chartRef.current?.timeScale().fitContent();
  }, [ticker, priceHistory]);

  const priceColor = direction === "up" ? "#3fb950" : direction === "down" ? "#f85149" : "#8b949e";
  const directionArrow = direction === "up" ? "▲" : direction === "down" ? "▼" : "";

  return (
    <div className="flex flex-col h-full" style={{ background: "#0d1117" }}>
      {/* Chart header */}
      <div
        className="flex items-center justify-between px-4 py-2 border-b shrink-0"
        style={{ borderColor: "#21262d" }}
      >
        <div className="flex items-center gap-3">
          <span className="text-base font-semibold mono" style={{ color: "#e6edf3" }}>
            {ticker ?? "Select a ticker"}
          </span>
          {ticker && currentPrice !== null && (
            <div className="flex items-center gap-1">
              <span
                className="mono text-lg font-semibold"
                style={{ color: priceColor, fontFamily: "var(--font-mono), monospace" }}
              >
                ${currentPrice.toFixed(2)}
              </span>
              <span className="text-sm" style={{ color: priceColor }}>
                {directionArrow}
              </span>
            </div>
          )}
        </div>
        {ticker && (
          <span className="text-xs" style={{ color: "#484f58" }}>Live</span>
        )}
      </div>

      {/* Chart area */}
      <div className="flex-1 relative min-h-0" ref={containerRef}>
        {(!ticker || (ticker && (priceHistory.get(ticker)?.length ?? 0) === 0)) && (
          <div className="absolute inset-0 flex items-center justify-center" style={{ color: "#484f58" }}>
            <div className="text-center">
              <svg
                className="mx-auto mb-2 opacity-40"
                width="48"
                height="48"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              <p className="text-sm">
                {ticker ? "Waiting for price history..." : "Click a ticker to view its chart"}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
