import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { backoffDelay, ChatSocket } from "@/lib/chat/socket";
import type { Connection } from "@/lib/chat/state";

import { asWebSocket, FakeWebSocket } from "./fakeSocket";

function make() {
  const connections: Connection[] = [];
  const opens: boolean[] = [];
  const events: unknown[] = [];
  const socket = new ChatSocket(
    "ws://api.test/ws/chat",
    {
      onEvent: (e) => events.push(e),
      onConnection: (c) => connections.push(c),
      onOpen: (reconnected) => opens.push(reconnected),
    },
    { WebSocketImpl: asWebSocket, wakingAfterMs: 3000, random: () => 0.5 },
  );
  return { socket, connections, opens, events };
}

describe("backoffDelay", () => {
  it("doubles up to the cap, with jitter", () => {
    const mid = () => 0.5;
    expect([0, 1, 2, 3, 4, 5].map((a) => backoffDelay(a, 15000, mid))).toEqual([
      1000, 2000, 4000, 8000, 15000, 15000,
    ]);
    expect(backoffDelay(0, 15000, () => 0)).toBe(800);
  });
});

describe("ChatSocket", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.reset();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("goes online, parses events and sends only when open", () => {
    const { socket, connections, opens, events } = make();
    socket.connect();
    expect(socket.send({ type: "ping" })).toBe(false);
    FakeWebSocket.latest().open();
    expect(connections).toEqual(["connecting", "online"]);
    expect(opens).toEqual([false]);
    expect(socket.send({ type: "ping" })).toBe(true);
    FakeWebSocket.latest().emit({ type: "pong" });
    FakeWebSocket.latest().onmessage?.({ data: "garbage" });
    expect(events).toEqual([{ type: "pong" }]);
  });

  it("shows 'waking' when the first connection is slow (cold start)", () => {
    const { socket, connections } = make();
    socket.connect();
    vi.advanceTimersByTime(3000);
    expect(connections).toContain("waking");
  });

  it("reconnects with backoff after a drop and reports the reconnect", () => {
    const { socket, connections, opens } = make();
    socket.connect();
    FakeWebSocket.latest().open();
    FakeWebSocket.latest().drop();
    expect(connections.at(-1)).toBe("reconnecting");
    expect(FakeWebSocket.instances).toHaveLength(1);
    vi.advanceTimersByTime(1000);
    expect(FakeWebSocket.instances).toHaveLength(2);
    FakeWebSocket.latest().open();
    expect(opens).toEqual([false, true]);
  });

  it("pings to keep the connection alive and stops after close", () => {
    const { socket } = make();
    socket.connect();
    const ws = FakeWebSocket.latest();
    ws.open();
    vi.advanceTimersByTime(25000);
    expect(ws.sentOfType("ping")).toHaveLength(1);
    socket.close();
    ws.drop();
    vi.advanceTimersByTime(60000);
    expect(FakeWebSocket.instances).toHaveLength(1);
  });
});
