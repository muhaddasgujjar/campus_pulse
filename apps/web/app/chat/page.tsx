import type { Metadata } from "next";

import { BrandMark } from "@/components/brand/BrandMark";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: `Chat · ${institution.productName}` };

/**
 * Chat shell (DESIGN.md 3.2). M1 placeholder only: header, empty state, disabled composer,
 * disclaimer. Streaming over the WebSocket, bubbles and sources arrive in M3.
 */
export default function ChatPage() {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-190 flex-col">
      <header className="sticky top-0 flex items-center gap-3 border-b border-border bg-bg px-4 py-3">
        <BrandMark size={40} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-semibold">{institution.productName}</span>
          <span className="truncate text-xs text-muted">{institution.name}</span>
        </div>
        <span className="flex items-center gap-2 text-xs text-muted">
          <span aria-hidden="true" className="size-2 rounded-(--radius-pill) bg-muted" />
          Not connected
        </span>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <BrandMark size={64} glow />
        <p className="text-lg">{institution.greeting}</p>
        <p className="text-sm text-muted">Chat arrives in milestone M3.</p>
      </main>

      <footer className="border-t border-border bg-bg px-4 pt-3 pb-4">
        <form className="flex items-center gap-2" aria-label="Message composer">
          <label htmlFor="composer" className="sr-only">
            Type a message
          </label>
          <input
            id="composer"
            type="text"
            disabled
            placeholder="Type a message…"
            className="min-h-11 flex-1 rounded-(--radius-pill) border border-border bg-surface-2 px-4 text-base text-text placeholder:text-muted disabled:cursor-not-allowed disabled:opacity-70"
          />
          <button
            type="submit"
            disabled
            className="min-h-11 rounded-(--radius-pill) bg-primary px-5 font-semibold text-on-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            Send
          </button>
        </form>
        <p className="mt-2 text-xs text-muted">{institution.disclaimer}</p>
      </footer>
    </div>
  );
}
