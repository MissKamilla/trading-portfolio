"use client";

import { useEffect, useRef, useState } from "react";
import type { PriceUpdate, ConnectionStatus } from "@/lib/types";

const SSE_URL = "/api/stream/prices";

interface UsePriceStreamResult {
  prices: Map<string, PriceUpdate>;
  connectionStatus: ConnectionStatus;
  priceHistory: Map<string, PriceUpdate[]>;
  lastUpdate: number;
}

export function usePriceStream(): UsePriceStreamResult {
  const [prices, setPrices] = useState<Map<string, PriceUpdate>>(new Map());
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected");
  const [lastUpdate, setLastUpdate] = useState<number>(0);

  // Store price history for sparklines (in-memory, keyed by ticker)
  const historyRef = useRef<Map<string, PriceUpdate[]>>(new Map());
  const [priceHistory, setPriceHistory] = useState<Map<string, PriceUpdate[]>>(new Map());

  const esRef = useRef<EventSource | null>(null);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef<number>(0);

  useEffect(() => {
    function connect() {
      if (esRef.current) {
        esRef.current.close();
      }

      setConnectionStatus("reconnecting");

      const es = new EventSource(SSE_URL);
      esRef.current = es;

      es.onopen = () => {
        setConnectionStatus("connected");
        retryCountRef.current = 0;
      };

      es.addEventListener("price", (event: MessageEvent) => {
        try {
          const update: PriceUpdate = JSON.parse(event.data);

          setPrices((prev) => {
            const next = new Map(prev);
            next.set(update.ticker, update);
            return next;
          });

          setLastUpdate(Date.now());

          const history = historyRef.current;
          const existing = history.get(update.ticker) ?? [];
          const updated = [...existing, update].slice(-60);
          history.set(update.ticker, updated);
          setPriceHistory(new Map(history));
        } catch {
          // Ignore malformed events
        }
      });

      es.onerror = () => {
        setConnectionStatus("reconnecting");
        es.close();

        const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 5000);
        retryCountRef.current += 1;

        if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      if (esRef.current) esRef.current.close();
      if (retryTimeoutRef.current) clearTimeout(retryTimeoutRef.current);
    };
  }, []);

  return { prices, connectionStatus, priceHistory, lastUpdate };
}
