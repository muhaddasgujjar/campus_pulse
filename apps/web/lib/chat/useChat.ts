"use client";

/**
 * Chat hook: reducer state + reconnecting socket + REST (history, feedback).
 *
 * - The conversation id and last answer id are kept in localStorage, so a reload shows the
 *   history (REST) and a reconnect resumes missed answers (CHAT-9).
 * - Questions are queued until the socket is open (cold start, COST-6) and resent after a
 *   reconnect if they were never acknowledged.
 * - Until the first `ack` returns the conversation id, later questions wait, so one chat
 *   never splits into two conversations.
 */

import { useCallback, useEffect, useReducer, useRef } from "react";

import { type FeedbackReason, fetchHistory, sendFeedback } from "@/lib/chat/api";
import { ChatSocket, type SocketOptions } from "@/lib/chat/socket";
import { getAccessToken } from "@/lib/auth";
import {
  awaitingAnswer,
  type ChatState,
  chatReducer,
  initialState,
  localId,
  unacknowledged,
} from "@/lib/chat/state";
import { publicConfig } from "@/lib/config";

const STORAGE_KEY = "campus-pulse.chat";
const RESUME_RETRY_MS = [4000, 10000];

type Saved = { conversationId: string | null; lastMessageId: string | null };

function loadSaved(): Saved {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const value = JSON.parse(raw) as Partial<Saved>;
      return {
        conversationId: typeof value.conversationId === "string" ? value.conversationId : null,
        lastMessageId: typeof value.lastMessageId === "string" ? value.lastMessageId : null,
      };
    }
  } catch {
    // storage blocked (private mode): start fresh
  }
  return { conversationId: null, lastMessageId: null };
}

function save(saved: Saved): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  } catch {
    // ignore
  }
}

export type UseChatOptions = {
  wsUrl?: string;
  apiUrl?: string;
  socket?: SocketOptions;
  /** The signed-in student's token, if any (AUTH-4). Defaults to the browser session. */
  getToken?: () => Promise<string | null>;
};

export function useChat(options: UseChatOptions = {}) {
  const wsUrl = options.wsUrl ?? publicConfig.wsUrl;
  const apiUrl = options.apiUrl ?? publicConfig.apiUrl;
  const socketOptions = options.socket;
  const getToken = options.getToken ?? getAccessToken;
  const token = useRef<string | null>(null);
  const [state, dispatch] = useReducer(chatReducer, undefined, () => initialState());
  const stateRef = useRef<ChatState>(state);
  const socketRef = useRef<ChatSocket | null>(null);
  const inFlight = useRef<Set<string>>(new Set()); // localIds sent, waiting for ack
  const resumeTimers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const loaded = useRef(false);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  /** Send queued questions that are not on the wire yet. Idempotent. */
  const flush = useCallback(() => {
    const socket = socketRef.current;
    if (!socket?.isOpen) return;
    const current = stateRef.current;
    const pending = unacknowledged(current);
    const waiting = new Set(pending.map((m) => m.localId));
    for (const id of inFlight.current) if (!waiting.has(id)) inFlight.current.delete(id);
    for (const message of pending) {
      if (inFlight.current.has(message.localId)) continue;
      // No conversation yet and one question already on the wire: wait for its ack.
      if (!current.conversationId && inFlight.current.size > 0) break;
      const sent = socket.send({
        type: "user_message",
        conversation_id: current.conversationId,
        text: message.text,
        modality: message.modality,
      });
      if (!sent) break;
      inFlight.current.add(message.localId);
    }
  }, []);

  const resume = useCallback(() => {
    const current = stateRef.current;
    if (!current.conversationId) return;
    socketRef.current?.send({
      type: "resume",
      conversation_id: current.conversationId,
      last_message_id: current.lastMessageId,
    });
  }, []);

  // Restore the saved conversation and its history once.
  useEffect(() => {
    if (loaded.current) return;
    loaded.current = true;
    const saved = loadSaved();
    void getToken()
      .catch(() => null)
      .then((found) => {
        token.current = found;
        if (found) socketRef.current?.send({ type: "auth", token: found });
        if (!saved.conversationId) return;
        void fetchHistory(saved.conversationId, apiUrl, found).then((messages) => {
          if (messages && saved.conversationId) {
            dispatch({ type: "history", messages, conversationId: saved.conversationId });
          }
        });
      });
  }, [apiUrl, getToken]);

  // The socket lives as long as the chat screen.
  useEffect(() => {
    if (!wsUrl) {
      dispatch({ type: "connection", connection: "offline" });
      return;
    }
    const timers = resumeTimers.current;
    const socket = new ChatSocket(
      `${wsUrl}/ws/chat`,
      {
        onEvent: (event) => dispatch({ type: "server", event, now: Date.now() }),
        onConnection: (connection) => dispatch({ type: "connection", connection }),
        onOpen: (reconnected) => {
          inFlight.current.clear(); // nothing unacknowledged survived the old socket
          // Who is asking goes first, so new chats are linked to the signed-in student.
          if (token.current) socket.send({ type: "auth", token: token.current });
          flush();
          if (!reconnected) return;
          resume();
          // The answer may still be running on the server: ask again a little later.
          for (const delay of RESUME_RETRY_MS) {
            timers.push(
              setTimeout(() => {
                if (awaitingAnswer(stateRef.current)) resume();
              }, delay),
            );
          }
        },
      },
      socketOptions,
    );
    socketRef.current = socket;
    socket.connect();
    const goneOffline = () => dispatch({ type: "connection", connection: "offline" });
    const backOnline = () => socket.retryNow();
    window.addEventListener("offline", goneOffline);
    window.addEventListener("online", backOnline);
    return () => {
      window.removeEventListener("offline", goneOffline);
      window.removeEventListener("online", backOnline);
      timers.forEach(clearTimeout);
      timers.length = 0;
      socket.close();
      socketRef.current = null;
    };
  }, [wsUrl, socketOptions, flush, resume]);

  // Flush whenever something may have unblocked the queue (ack, reconnect, new question).
  useEffect(() => {
    flush();
  }, [state.messages, state.conversationId, state.connection, flush]);

  useEffect(() => {
    if (!loaded.current) return;
    save({ conversationId: state.conversationId, lastMessageId: state.lastMessageId });
  }, [state.conversationId, state.lastMessageId]);

  /** Send a question. Voice messages send their transcript with modality "voice" (VOI-3). */
  const send = useCallback(
    (text: string, voice?: { seconds: number | null }) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      dispatch({
        type: "send",
        localId: localId("u"),
        text: trimmed,
        now: Date.now(),
        modality: voice ? "voice" : "text",
        seconds: voice?.seconds ?? null,
      });
    },
    [],
  );

  const retry = useCallback((failedLocalId: string) => {
    const failed = stateRef.current.messages.find((m) => m.localId === failedLocalId);
    if (failed) {
      dispatch({
        type: "send",
        localId: localId("u"),
        text: failed.text,
        now: Date.now(),
        modality: failed.modality,
        seconds: failed.seconds,
      });
    }
  }, []);

  const rate = useCallback(
    async (messageId: string, rating: 1 | -1, reason?: FeedbackReason, comment?: string) => {
      const ok = await sendFeedback(
        { message_id: messageId, rating, reason, comment: comment?.trim() || undefined },
        apiUrl,
      );
      if (ok) dispatch({ type: "rated", id: messageId, rating });
      return ok;
    },
    [apiUrl],
  );

  const newChat = useCallback(() => {
    inFlight.current.clear();
    dispatch({ type: "reset" });
  }, []);

  const dismissNotice = useCallback(() => dispatch({ type: "dismissNotice" }), []);

  /** After the student signs in or out: later questions are linked to the new identity. */
  const setAuthToken = useCallback((next: string | null) => {
    token.current = next;
    if (next) socketRef.current?.send({ type: "auth", token: next });
  }, []);

  return { state, send, retry, rate, newChat, dismissNotice, setAuthToken };
}
