"use client";

import { useState, useCallback, useRef } from "react";
import type { PointerEvent } from "react";
import Header from "@/components/Header";
import Watchlist from "@/components/Watchlist";
import MainChart from "@/components/MainChart";
import PortfolioHeatmap from "@/components/PortfolioHeatmap";
import PnLChart from "@/components/PnLChart";
import PositionsTable from "@/components/PositionsTable";
import TradeBar from "@/components/TradeBar";
import ChatPanel from "@/components/ChatPanel";
import { usePriceStream } from "@/hooks/usePriceStream";
import { usePortfolio } from "@/hooks/usePortfolio";
import { useChat } from "@/hooks/useChat";

export default function Home() {
  const [requestedTicker, setRequestedTicker] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [watchlistWidth, setWatchlistWidth] = useState(320);
  const resizingRef = useRef(false);

  const { prices, connectionStatus, priceHistory } = usePriceStream();
  const { portfolio, history, watchlist, loading, refresh } = usePortfolio(prices);
  const { messages, isLoading: chatLoading, sendMessage } = useChat(refresh);

  const handleTradeExecuted = useCallback(() => {
    refresh();
  }, [refresh]);

  const handleResizeStart = useCallback((event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    resizingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const handleResizeMove = useCallback((event: PointerEvent<HTMLDivElement>) => {
    if (!resizingRef.current) return;
    const nextWidth = Math.min(Math.max(event.clientX, 280), 520);
    setWatchlistWidth(nextWidth);
  }, []);

  const handleResizeEnd = useCallback((event: PointerEvent<HTMLDivElement>) => {
    resizingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const selectedTicker =
    watchlist.length === 0
      ? null
      : requestedTicker && watchlist.some((item) => item.ticker === requestedTicker)
        ? requestedTicker
        : watchlist[0].ticker;
  const currentPrice = selectedTicker ? prices.get(selectedTicker)?.price ?? null : null;
  const currentDirection = selectedTicker ? (prices.get(selectedTicker)?.direction ?? null) : null;

  return (
    <div className="flex flex-col h-full overflow-hidden" style={{ background: "#0d1117" }}>
      {/* Header */}
      <Header
        totalValue={portfolio?.total_value ?? null}
        cashBalance={portfolio?.cash_balance ?? null}
        connectionStatus={connectionStatus}
      />

      {/* Body */}
      <div className="flex flex-1 min-h-0 overflow-hidden relative">
        {/* Left: Watchlist */}
        <div
          className="shrink-0 border-r flex flex-col relative"
          style={{ width: watchlistWidth, borderColor: "#21262d" }}
        >
          <div className="flex-1 min-h-0 overflow-hidden">
            <Watchlist
              items={watchlist}
              priceHistory={priceHistory}
              selectedTicker={selectedTicker}
              onSelectTicker={(t) => setRequestedTicker(t)}
              onRefresh={refresh}
            />
          </div>

          {/* Trade bar below watchlist */}
          <TradeBar
            key={selectedTicker ?? "no-selection"}
            selectedTicker={selectedTicker}
            cashBalance={portfolio?.cash_balance ?? null}
            onTradeExecuted={handleTradeExecuted}
          />

          <div
            className="absolute top-0 right-[-4px] h-full w-2 cursor-col-resize z-30 hover:bg-[#58a6ff]/25"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize watchlist panel"
            onPointerDown={handleResizeStart}
            onPointerMove={handleResizeMove}
            onPointerUp={handleResizeEnd}
            onPointerCancel={handleResizeEnd}
          />
        </div>

        {/* Center: Charts */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Top row: Main chart + Heatmap */}
          <div className="flex flex-1 min-h-0 border-b overflow-hidden" style={{ borderColor: "#21262d" }}>
            <div className="flex-1 min-w-0 overflow-hidden" style={{ borderRight: "1px solid #21262d" }}>
              <MainChart
                ticker={selectedTicker}
                priceHistory={priceHistory}
                currentPrice={currentPrice}
                direction={currentDirection}
              />
            </div>
            <div className="w-72 shrink-0">
              <PortfolioHeatmap
                positions={portfolio?.positions ?? []}
                totalValue={portfolio?.total_value ?? 0}
              />
            </div>
          </div>

          {/* Bottom row: P&L chart + Positions table */}
          <div className="flex flex-1 min-h-0 overflow-hidden">
            <div className="flex-1 min-w-0 overflow-hidden" style={{ borderRight: "1px solid #21262d" }}>
              <PnLChart history={history} />
            </div>
            <div className="flex-1 min-w-0 overflow-hidden">
              <PositionsTable positions={portfolio?.positions ?? []} />
            </div>
          </div>
        </div>

        {/* Right: Chat Panel */}
        <ChatPanel
          messages={messages}
          isLoading={chatLoading}
          onSend={sendMessage}
          isOpen={chatOpen}
          onToggle={() => setChatOpen((o) => !o)}
        />
      </div>

      {/* Loading overlay */}
      {loading && (
        <div
          className="absolute inset-0 flex items-center justify-center z-20"
          style={{ background: "rgba(13,17,23,0.7)" }}
        >
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: "#58a6ff", borderTopColor: "transparent" }} />
            <span className="text-sm" style={{ color: "#8b949e" }}>Loading market data...</span>
          </div>
        </div>
      )}
    </div>
  );
}
