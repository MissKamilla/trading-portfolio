"use client";

import { useRef, useEffect, useState, type FormEvent } from "react";
import type { ChatMessage } from "@/lib/types";

interface ChatPanelProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onSend: (text: string) => void;
  isOpen: boolean;
  onToggle: () => void;
}

function LoadingDots() {
  return (
    <div className="flex gap-1 items-center px-3 py-2">
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="w-1.5 h-1.5 rounded-full animate-bounce"
          style={{
            background: "#58a6ff",
            animationDelay: `${i * 150}ms`,
          }}
        />
      ))}
    </div>
  );
}

function TradeActionBadge({ ticker, side, quantity, status }: {
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  status: string;
}) {
  const isBuy = side === "buy";
  const bgColor = isBuy ? "rgba(35,134,54,0.2)" : "rgba(182,35,36,0.2)";
  const borderColor = isBuy ? "#238636" : "#b62324";
  const textColor = isBuy ? "#3fb950" : "#f85149";

  return (
    <div
      className="flex items-center gap-2 px-3 py-2 rounded text-xs my-1"
      style={{ background: bgColor, border: `1px solid ${borderColor}` }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={textColor} strokeWidth="2">
        {isBuy ? (
          <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
        ) : (
          <polyline points="23 18 13.5 8.5 8.5 13.5 1 6" />
        )}
        {isBuy ? <polyline points="17 6 23 6 23 12" /> : <polyline points="17 18 23 18 23 12" />}
      </svg>
      <span style={{ color: textColor }}>
        {isBuy ? "Bought" : "Sold"} {quantity} {ticker}
      </span>
      {status === "failed" && (
        <span className="ml-auto" style={{ color: "#f85149" }}>Failed</span>
      )}
      {status === "executed" && (
        <svg className="ml-auto" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={textColor} strokeWidth="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </div>
  );
}

function WatchlistChangeBadge({ action, ticker, status }: {
  action: "add" | "remove";
  ticker: string;
  status: string;
}) {
  const isAdd = action === "add";
  const color = isAdd ? "#3fb950" : "#f85149";
  return (
    <div
      className="flex items-center gap-2 px-3 py-2 rounded text-xs my-1"
      style={{ background: "rgba(88,166,255,0.1)", border: "1px solid #30363d" }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2">
        {isAdd ? (
          <><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></>
        ) : (
          <><line x1="5" y1="12" x2="19" y2="12" /></>
        )}
      </svg>
      <span style={{ color }}>
        {isAdd ? "Added" : "Removed"} {ticker} {isAdd ? "to" : "from"} watchlist
      </span>
      {status === "executed" && (
        <svg className="ml-auto" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      )}
    </div>
  );
}

export default function ChatPanel({ messages, isLoading, onSend, isOpen, onToggle }: ChatPanelProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isLoading) return;
    onSend(text);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <>
      {/* Toggle button (always visible) */}
      <button
        onClick={onToggle}
        className="absolute top-1 right-4 z-10 flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors"
        style={{
          background: isOpen ? "#1c2128" : "#21262d",
          color: "#8b949e",
          border: "1px solid #30363d",
        }}
        title={isOpen ? "Close chat" : "Open AI Chat"}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        AI Copilot
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          style={{ transform: isOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 200ms" }}
        >
          <polyline points="18 15 12 9 6 15" />
        </svg>
      </button>

      {/* Panel */}
      <div
        className="flex flex-col border-l overflow-hidden"
        style={{
          background: "#161b22",
          borderColor: "#21262d",
          width: isOpen ? "340px" : "0",
          transition: "width 200ms ease-in-out",
          flexShrink: 0,
        }}
      >
        {isOpen && (
          <>
            {/* Panel header */}
            <div
              className="flex items-center justify-between px-3 py-2 border-b shrink-0"
              style={{ borderColor: "#21262d" }}
            >
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "#58a6ff" }}>
                  AI Copilot
                </span>
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{ background: "rgba(88,166,255,0.1)", color: "#58a6ff" }}
                >
                  FinAlly
                </span>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
              {messages.length === 0 && (
                <div className="text-center py-8" style={{ color: "#484f58" }}>
                  <svg className="mx-auto mb-2 opacity-50" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                  </svg>
                  <p className="text-sm">Ask me about your portfolio, trades, or market analysis.</p>
                </div>
              )}

              {messages.map((msg, i) => (
                <div key={i}>
                  {/* Message bubble */}
                  <div
                    className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"}`}
                  >
                    <div
                      className="max-w-[85%] px-3 py-2 rounded-lg text-sm leading-relaxed"
                      style={{
                        background: msg.role === "user" ? "#238636" : "#1c2128",
                        color: "#e6edf3",
                        border: msg.role === "user" ? "1px solid #2ea043" : "1px solid #30363d",
                      }}
                    >
                      {msg.content}
                    </div>
                  </div>

                  {/* Trade actions */}
                  {msg.trades && msg.trades.length > 0 && (
                    <div className="mt-1">
                      {msg.trades.map((trade, j) => (
                        <TradeActionBadge
                          key={j}
                          ticker={trade.ticker}
                          side={trade.side}
                          quantity={trade.quantity}
                          status={trade.status}
                        />
                      ))}
                    </div>
                  )}

                  {/* Watchlist changes */}
                  {msg.watchlist_changes && msg.watchlist_changes.length > 0 && (
                    <div className="mt-1">
                      {msg.watchlist_changes.map((wc, j) => (
                        <WatchlistChangeBadge
                          key={j}
                          action={wc.action}
                          ticker={wc.ticker}
                          status={wc.status}
                        />
                      ))}
                    </div>
                  )}
                </div>
              ))}

              {isLoading && (
                <div className="flex items-start gap-2">
                  <div
                    className="px-3 py-2 rounded-lg text-sm"
                    style={{ background: "#1c2128", border: "1px solid #30363d", color: "#e6edf3" }}
                  >
                    <LoadingDots />
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <form
              className="flex gap-2 p-3 border-t shrink-0"
              style={{ borderColor: "#21262d" }}
              onSubmit={handleSubmit}
            >
              <textarea
                ref={inputRef}
                className="flex-1 px-3 py-2 text-sm bg-[#0d1117] border rounded resize-none text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff] transition-colors"
                style={{ borderColor: "#30363d" }}
                placeholder="Ask the AI..."
                rows={2}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isLoading}
              />
              <button
                type="submit"
                className="px-3 py-2 rounded transition-colors disabled:opacity-40 self-end"
                style={{ background: "#58a6ff", color: "#0d1117" }}
                disabled={!input.trim() || isLoading}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </form>
          </>
        )}
      </div>
    </>
  );
}
