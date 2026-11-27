/** A controllable WebSocket stand-in for jsdom tests. */
export class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  readyState = FakeWebSocket.CONNECTING;
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  static latest(): FakeWebSocket {
    const socket = FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
    if (!socket) throw new Error("no socket opened");
    return socket;
  }

  static reset(): void {
    FakeWebSocket.instances = [];
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.readyState = FakeWebSocket.CLOSED;
  }

  // test controls
  open(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  drop(): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }

  emit(event: object): void {
    this.onmessage?.({ data: JSON.stringify(event) });
  }

  sentOfType(type: string): Record<string, unknown>[] {
    return this.sent.filter(
      (item): item is Record<string, unknown> =>
        typeof item === "object" && item !== null && (item as { type?: unknown }).type === type,
    );
  }
}

export const asWebSocket = FakeWebSocket as unknown as typeof WebSocket;

/** One full answer, as the API sends it. */
export function answerEvents(opts: {
  messageId: string;
  conversationId: string;
  text: string;
  sources?: object[];
  fallback?: boolean;
  office?: object | null;
}): object[] {
  return [
    { type: "status", stage: "searching" },
    { type: "sources", message_id: opts.messageId, items: opts.sources ?? [] },
    { type: "token", message_id: opts.messageId, text: opts.text },
    {
      type: "final",
      message_id: opts.messageId,
      conversation_id: opts.conversationId,
      fallback: opts.fallback ?? false,
      cache_hit: false,
      office: opts.office ?? null,
      replay: false,
    },
  ];
}
