"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import type { ChatMessage, ChatResponse } from "@/lib/types";
import * as api from "@/lib/api";

interface UseChatResult {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (text: string) => Promise<void>;
}

export function useChat(onTradeExecuted?: () => void): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onTradeExecutedRef = useRef(onTradeExecuted);

  useEffect(() => {
    onTradeExecutedRef.current = onTradeExecuted;
  }, [onTradeExecuted]);

  const sendMessage = useCallback(async (text: string) => {
    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);
    setError(null);

    try {
      const res: ChatResponse = await api.sendChat(text);

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: res.message,
        trades: res.trades,
        watchlist_changes: res.watchlist_changes,
        timestamp: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // Notify parent to refresh portfolio after trade actions
      if (
        res.trades.length > 0 ||
        res.watchlist_changes.length > 0
      ) {
        onTradeExecutedRef.current?.();
      }
    } catch (e: unknown) {
      const msg =
        (e as { error?: { message?: string } })?.error?.message ??
        "Failed to get a response. Please try again.";
      setError(msg);

      const errorMsg: ChatMessage = {
        role: "assistant",
        content: `Error: ${msg}`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  return { messages, isLoading, error, sendMessage };
}
