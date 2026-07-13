"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type { Portfolio, PortfolioSnapshot, WatchlistItem, PriceUpdate } from "@/lib/types";
import * as api from "@/lib/api";

export function usePortfolio(prices: Map<string, PriceUpdate>) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const portfolioRef = useRef<Portfolio | null>(null);
  const watchlistRef = useRef<WatchlistItem[]>([]);

  const mergePrices = useCallback((pf: Portfolio): Portfolio => {
    const updatedPositions = pf.positions.map((pos) => {
      const live = prices.get(pos.ticker);
      if (!live || live.price === null) return pos;
      const market_value = live.price * pos.quantity;
      const unrealized_pl = (live.price - pos.avg_cost) * pos.quantity;
      const unrealized_pl_percent = pos.avg_cost
        ? ((live.price - pos.avg_cost) / pos.avg_cost) * 100
        : 0;
      return {
        ...pos,
        current_price: live.price,
        market_value,
        unrealized_pl,
        unrealized_pl_percent,
      };
    });

    const posValue = updatedPositions.reduce((s, p) => s + p.market_value, 0);
    const totalValue = pf.cash_balance + posValue;
    const unrealizedPl = updatedPositions.reduce((s, p) => s + p.unrealized_pl, 0);
    return { ...pf, positions: updatedPositions, total_value: totalValue, unrealized_pl: unrealizedPl };
  }, [prices]);

  const mergeWatchlist = useCallback((items: WatchlistItem[]): WatchlistItem[] => {
    return items.map((item) => {
      const live = prices.get(item.ticker);
      if (!live) return item;
      return {
        ...item,
        price: live.price,
        previous_price: live.previous_price,
        change: live.change,
        change_percent: live.change_percent,
        direction: live.direction,
        price_status: live.price_status,
        timestamp: live.timestamp,
      };
    });
  }, [prices]);

  // Fetch initial data
  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [pf, hist, wl] = await Promise.all([
          api.getPortfolio(),
          api.getPortfolioHistory(),
          api.getWatchlist(),
        ]);
        portfolioRef.current = pf;
        watchlistRef.current = wl.items;
        setPortfolio(pf);
        setHistory(hist.items);
        setWatchlist(wl.items);
      } catch (e: unknown) {
        const msg =
          (e as { error?: { message?: string } })?.error?.message ??
          "Failed to load data.";
        setError(msg);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  // Merge live prices into portfolio whenever prices change
  useEffect(() => {
    if (!portfolioRef.current || prices.size === 0) return;
    const merged = mergePrices(portfolioRef.current);
    portfolioRef.current = merged;
    setPortfolio(merged);
    setWatchlist((prev) => (prev.length ? mergeWatchlist(prev) : prev));
  }, [prices, mergePrices, mergeWatchlist]);

  const refresh = useCallback(() => {
    async function load() {
      try {
        const [pf, hist, wl] = await Promise.all([
          api.getPortfolio(),
          api.getPortfolioHistory(),
          api.getWatchlist(),
        ]);
        const merged = prices.size > 0 ? mergePrices(pf) : pf;
        portfolioRef.current = merged;
        watchlistRef.current = wl.items;
        setPortfolio(merged);
        setHistory(hist.items);
        setWatchlist(wl.items);
      } catch (e: unknown) {
        const msg =
          (e as { error?: { message?: string } })?.error?.message ??
          "Failed to load data.";
        setError(msg);
      }
    }
    load();
  }, [mergePrices, prices]);

  return { portfolio, history, watchlist, loading, error, refresh };
}
