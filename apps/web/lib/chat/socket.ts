/**
 * Reconnecting WebSocket for /ws/chat (CHAT-9, COST-6).
 *
 * - Retries with exponential backoff (1 s, 2 s, 4 s ... up to 15 s) plus jitter.
 * - Reports "waking" when the first connection takes long or fails: on Render's free plan the
 *   API sleeps after 15 minutes and needs up to a minute to start.
 * - Calls `onOpen(reconnected)` on every open, so the caller can resend unacknowledged
 *   questions and `resume` missed answers.
 * - Pings every 25 s so idle proxies keep the connection.
 */

import { type ClientEvent, parseServerEvent, type ServerEvent } from "@/lib/chat/protocol";
import type { Connection } from "@/lib/chat/state";

export type SocketHandlers = {
  onEvent: (event: ServerEvent) => void;
  onConnection: (connection: Connection) => void;
  onOpen: (reconnected: boolean) => void;
};

export type SocketOptions = {
  WebSocketImpl?: typeof WebSocket;
  wakingAfterMs?: number;
  maxDelayMs?: number;
  pingEveryMs?: number;
  random?: () => number;
};

export function backoffDelay(attempt: number, maxDelayMs = 15000, random = Math.random): number {
  const base = Math.min(1000 * 2 ** attempt, maxDelayMs);
  return Math.round(base * (0.8 + 0.4 * random()));
}

export class ChatSocket {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private everOpened = false;
  private stopped = false;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private wakingTimer: ReturnType<typeof setTimeout> | null = null;
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private readonly Impl: typeof WebSocket;
  private readonly opts: Required<Omit<SocketOptions, "WebSocketImpl">>;

  constructor(
    private readonly url: string,
    private readonly handlers: SocketHandlers,
    options: SocketOptions = {},
  ) {
    this.Impl = options.WebSocketImpl ?? WebSocket;
    this.opts = {
      wakingAfterMs: options.wakingAfterMs ?? 3000,
      maxDelayMs: options.maxDelayMs ?? 15000,
      pingEveryMs: options.pingEveryMs ?? 25000,
      random: options.random ?? Math.random,
    };
  }

  get isOpen(): boolean {
    return this.ws?.readyState === this.Impl.OPEN;
  }

  connect(): void {
    this.stopped = false;
    this.open();
  }

  /** Send now if open. Returns false when not connected (the caller keeps the message). */
  send(event: ClientEvent): boolean {
    if (!this.ws || !this.isOpen) return false;
    this.ws.send(JSON.stringify(event));
    return true;
  }

  close(): void {
    this.stopped = true;
    this.clearTimers();
    this.ws?.close();
    this.ws = null;
  }

  /** Try again right away (for example when the browser comes back online). */
  retryNow(): void {
    if (this.stopped || this.isOpen) return;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    this.retryTimer = null;
    this.attempt = 0;
    this.open();
  }

  private open(): void {
    if (this.stopped) return;
    this.handlers.onConnection(this.everOpened ? "reconnecting" : "connecting");
    if (!this.everOpened && !this.wakingTimer) {
      this.wakingTimer = setTimeout(() => {
        if (!this.isOpen && !this.stopped) this.handlers.onConnection("waking");
      }, this.opts.wakingAfterMs);
    }
    let ws: WebSocket;
    try {
      ws = new this.Impl(this.url);
    } catch {
      this.scheduleRetry();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      const reconnected = this.everOpened;
      this.everOpened = true;
      this.attempt = 0;
      if (this.wakingTimer) clearTimeout(this.wakingTimer);
      this.wakingTimer = null;
      this.handlers.onConnection("online");
      this.startPing();
      this.handlers.onOpen(reconnected);
    };
    ws.onmessage = (message: MessageEvent) => {
      if (typeof message.data !== "string") return;
      const event = parseServerEvent(message.data);
      if (event) this.handlers.onEvent(event);
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.stopPing();
      this.scheduleRetry();
    };
    ws.onerror = () => {
      // onclose follows and schedules the retry
    };
  }

  private scheduleRetry(): void {
    if (this.stopped) return;
    if (this.everOpened) this.handlers.onConnection("reconnecting");
    else if (this.attempt > 0) this.handlers.onConnection("waking");
    const delay = backoffDelay(this.attempt, this.opts.maxDelayMs, this.opts.random);
    this.attempt += 1;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.open();
    }, delay);
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = setInterval(() => this.send({ type: "ping" }), this.opts.pingEveryMs);
  }

  private stopPing(): void {
    if (this.pingTimer) clearInterval(this.pingTimer);
    this.pingTimer = null;
  }

  private clearTimers(): void {
    this.stopPing();
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.wakingTimer) clearTimeout(this.wakingTimer);
    this.retryTimer = null;
    this.wakingTimer = null;
  }
}
