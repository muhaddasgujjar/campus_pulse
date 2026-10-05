import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WelcomePage from "@/app/page";
import ChatPage from "@/app/chat/page";
import { wakeApi } from "@/lib/wake";

describe("welcome page", () => {
  it("renders the product name, greeting and a Start chat link to /chat", () => {
    render(<WelcomePage />);
    expect(screen.getByRole("heading", { level: 1, name: "Campus Pulse AI" })).toBeInTheDocument();
    expect(screen.getByText(/Ask me anything about LGU/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start chat" })).toHaveAttribute("href", "/chat");
  });
});

describe("chat shell", () => {
  it("shows a disabled composer and the disclaimer", () => {
    render(<ChatPage />);
    expect(screen.getByLabelText("Type a message")).toBeDisabled();
    expect(screen.getByText(/Please confirm important decisions/)).toBeInTheDocument();
  });
});

describe("supabase client", () => {
  it("is null when the public Supabase env vars are not set", async () => {
    const { getSupabaseBrowserClient } = await import("@/lib/supabase");
    expect(getSupabaseBrowserClient()).toBeNull();
  });
});

describe("wakeApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("pings /healthz once when an API URL is set", () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    wakeApi("http://api.test");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("http://api.test/healthz");
  });

  it("does nothing without an API URL", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    wakeApi(undefined);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("swallows network errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    expect(() => wakeApi("http://api.test")).not.toThrow();
    await Promise.resolve();
  });
});
