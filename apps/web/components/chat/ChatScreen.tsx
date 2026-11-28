"use client";

import { CircleAlert, Headphones, SquarePen, UserRound, WifiOff } from "lucide-react";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { BrandMark } from "@/components/brand/BrandMark";
import { Composer, type VoiceOptions } from "@/components/chat/Composer";
import { DeadlinesCard } from "@/components/chat/DeadlinesCard";
import { ProfileSheet } from "@/components/chat/ProfileSheet";
import { BotMessage, UserBubble } from "@/components/chat/Messages";
import { LiveOverlay } from "@/components/live/LiveOverlay";
import { accountApi } from "@/lib/account";
import { getAccessToken } from "@/lib/auth";
import { fetchConfig, type PublicConfig } from "@/lib/chat/api";
import type { Connection } from "@/lib/chat/state";
import { type UseChatOptions, useChat } from "@/lib/chat/useChat";
import { institution } from "@/lib/institution";
import type { LiveDeps } from "@/lib/voice/live";
import { canSpeak, recognitionCtor } from "@/lib/voice/support";

const noSubscribe = () => () => undefined;
const liveSupported = () => recognitionCtor() !== null && canSpeak();

const CONNECTION_LABEL: Record<Connection, string> = {
  connecting: "Connecting…",
  waking: "Waking up…",
  online: "Online",
  reconnecting: "Reconnecting…",
  offline: "Offline",
};

const DOT: Record<Connection, string> = {
  connecting: "bg-warning",
  waking: "bg-warning",
  online: "bg-success",
  reconnecting: "bg-warning",
  offline: "bg-danger",
};

function Chips({
  items,
  onPick,
  label,
  wrap = false,
}: {
  items: string[];
  onPick: (q: string) => void;
  label: string;
  wrap?: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <ul
      aria-label={label}
      className={`flex gap-2 ${wrap ? "flex-wrap justify-center" : "overflow-x-auto pb-1"}`}
    >
      {items.map((question) => (
        <li key={question} className="shrink-0">
          <button
            type="button"
            onClick={() => onPick(question)}
            className="min-h-11 rounded-(--radius-pill) border border-border-teal px-4 text-sm text-accent hover:bg-surface-teal"
          >
            {question}
          </button>
        </li>
      ))}
    </ul>
  );
}

function Banner({ tone, children }: { tone: "warning" | "danger"; children: React.ReactNode }) {
  return (
    <div
      role="status"
      className={`flex items-center gap-2 border-b border-border bg-surface-teal px-4 py-2 text-sm ${tone === "danger" ? "text-danger" : "text-warning"}`}
    >
      {children}
    </div>
  );
}

/** The chat screen (DESIGN.md Section 3.2): header, messages, quick replies, composer. */
export function ChatScreen({
  chatOptions,
  voiceOptions,
  liveOptions,
}: {
  chatOptions?: UseChatOptions;
  voiceOptions?: VoiceOptions;
  /** Overrides browser detection and APIs for live mode (tests). */
  liveOptions?: { enabled?: boolean; deps?: LiveDeps };
}) {
  const { state, send, retry, rate, newChat, dismissNotice, setAuthToken } = useChat(chatOptions);
  const [profileOpen, setProfileOpen] = useState(false);
  const [program, setProgram] = useState<string | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [editRequest, setEditRequest] = useState<{ text: string; nonce: number } | null>(null);
  const [liveOpen, setLiveOpen] = useState(false);
  const [liveNote, setLiveNote] = useState<string | null>(null);
  const detectedLive = useSyncExternalStore(noSubscribe, liveSupported, () => false);
  const canGoLive = liveOptions?.enabled ?? detectedLive;
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void fetchConfig(chatOptions?.apiUrl).then(setConfig);
  }, [chatOptions?.apiUrl]);

  // A returning signed-in student: their program filters the deadlines card.
  useEffect(() => {
    void getAccessToken().then(async (token) => {
      if (!token) return;
      const me = await accountApi.me().catch(() => null);
      if (me) setProgram(me.program);
    });
  }, []);

  const starters = useMemo(() => config?.starter_questions ?? [], [config]);
  const disclaimer = config?.disclaimer || institution.disclaimer;
  const name = config?.institution_name || institution.name;
  const { messages, connection, notice } = state;
  const busy = messages.some((m) => m.role === "assistant" && m.status === "streaming");
  const last = messages[messages.length - 1];

  const quickReplies = useMemo(() => {
    const asked = new Set(messages.filter((m) => m.role === "user").map((m) => m.text));
    return starters.filter((q) => !asked.has(q)).slice(0, 4);
  }, [messages, starters]);

  const lastText = last?.text;
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, lastText]);

  const latestAnswer = [...messages].reverse().find((m) => m.role === "assistant" && m.status === "done");

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-190 flex-col">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg px-4 py-3">
        <BrandMark size={40} />
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate font-semibold">{institution.productName}</span>
          <span className="truncate text-xs text-muted">{name}</span>
        </div>
        <span className="flex items-center gap-2 text-xs text-muted" aria-live="polite">
          <span aria-hidden="true" className={`size-2 rounded-(--radius-pill) ${DOT[connection]}`} />
          {CONNECTION_LABEL[connection]}
        </span>
        <button
          type="button"
          onClick={() => {
            setLiveNote(null);
            setLiveOpen(true);
          }}
          disabled={!canGoLive || connection === "offline"}
          aria-label="Live mode"
          title={canGoLive ? "Talk hands-free" : "Live mode works in Chrome and Edge"}
          className="inline-flex size-11 items-center justify-center rounded-(--radius-pill) text-muted hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Headphones size={20} strokeWidth={1.75} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => setProfileOpen(true)}
          aria-label="Your profile"
          className="inline-flex size-11 items-center justify-center rounded-(--radius-pill) text-muted hover:bg-surface-2"
        >
          <UserRound size={20} strokeWidth={1.75} aria-hidden="true" />
        </button>
        {messages.length > 0 && (
          <button
            type="button"
            onClick={newChat}
            aria-label="New chat"
            className="inline-flex size-11 items-center justify-center rounded-(--radius-pill) text-muted hover:bg-surface-2"
          >
            <SquarePen size={20} strokeWidth={1.75} aria-hidden="true" />
          </button>
        )}
      </header>

      {liveNote && (
        <Banner tone="warning">
          <span className="flex-1">{liveNote}</span>
          <button type="button" onClick={() => setLiveNote(null)} className="text-accent underline">
            Dismiss
          </button>
        </Banner>
      )}
      {profileOpen && (
        <ProfileSheet
          onClose={() => setProfileOpen(false)}
          onSaved={(profile, token) => {
            setProgram(profile.program);
            setAuthToken(token);
          }}
          onDeleted={() => {
            setProfileOpen(false);
            setProgram(null);
            setAuthToken(null);
            newChat();
          }}
        />
      )}
      {liveOpen && (
        <LiveOverlay
          messages={messages}
          notice={notice}
          onAsk={(text) => send(text, { seconds: null })}
          onClose={(note) => {
            setLiveOpen(false);
            if (note) setLiveNote(note);
          }}
          deps={liveOptions?.deps}
        />
      )}
      {connection === "waking" && (
        <Banner tone="warning">Waking up the assistant. This can take up to a minute the first time.</Banner>
      )}
      {connection === "offline" && (
        <Banner tone="danger">
          <WifiOff size={16} strokeWidth={1.75} aria-hidden="true" />
          You&apos;re offline. Reconnecting…
        </Banner>
      )}
      {connection === "reconnecting" && <Banner tone="warning">Connection lost. Reconnecting…</Banner>}

      <main className="flex flex-1 flex-col gap-4 px-4 py-4">
        {messages.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
            <BrandMark size={64} glow />
            <p className="text-lg">{institution.greeting}</p>
            <Chips items={starters} onPick={send} label="Starter questions" wrap />
            <DeadlinesCard program={program} onAsk={send} />
          </div>
        ) : (
          <div className="flex flex-col gap-4" aria-live="polite" aria-relevant="additions">
            {messages.map((message, index) =>
              message.role === "user" ? (
                <UserBubble
                  key={message.localId}
                  message={message}
                  onRetry={retry}
                  onEdit={(text) => setEditRequest({ text, nonce: Date.now() })}
                />
              ) : (
                <BotMessage
                  key={message.localId}
                  message={message}
                  onRate={rate}
                  showAvatar={messages[index - 1]?.role !== "assistant"}
                />
              ),
            )}
          </div>
        )}

        {notice && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-(--radius-md) border border-border bg-surface-2 px-4 py-3 text-sm"
          >
            <CircleAlert size={16} strokeWidth={1.75} aria-hidden="true" className="mt-0.5 shrink-0 text-warning" />
            <p className="flex-1">{notice.message}</p>
            <button type="button" onClick={dismissNotice} className="text-accent underline">
              Dismiss
            </button>
          </div>
        )}

        {messages.length > 0 && !busy && latestAnswer && latestAnswer === last && (
          <Chips items={quickReplies} onPick={send} label="Quick replies" />
        )}
        <div ref={bottom} />
      </main>

      <Composer
        onSend={(text) => send(text)}
        onSendVoice={(transcript, seconds) => send(transcript, { seconds: Math.round(seconds) })}
        disabled={connection === "offline"}
        disclaimer={disclaimer}
        editRequest={editRequest}
        voice={{ apiUrl: chatOptions?.apiUrl, ...voiceOptions }}
      />
    </div>
  );
}
