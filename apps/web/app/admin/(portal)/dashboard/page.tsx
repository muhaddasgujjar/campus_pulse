"use client";

import { CircleAlert, Clock, MessageCircleQuestion, ThumbsDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useAdmin } from "@/components/admin/AdminShell";
import { CategoryBars, DailyBars } from "@/components/admin/charts";
import { Card, Expiry, Loading, Notice, PageHeader, Table, CELL, ROW, todayIso } from "@/components/admin/ui";
import { adminApi, type Approval, type Metrics, type ReviewItem } from "@/lib/admin/api";

function percent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="flex flex-col gap-1">
      <p className="text-xs text-muted uppercase">{label}</p>
      <p className="text-3xl font-bold tabular-nums">{value}</p>
      {note ? <p className="text-xs text-muted">{note}</p> : null}
    </Card>
  );
}

function Usage({ metrics }: { metrics: Metrics }) {
  const mb = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(0)} MB`;
  const db = metrics.database_bytes;
  const share = db === null ? null : db / metrics.database_limit_bytes;
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold">Free-tier usage today</h2>
      <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
        <div>
          <dt className="text-muted">AI calls</dt>
          <dd className="text-lg font-semibold tabular-nums">{metrics.usage_today.llm_calls ?? 0}</dd>
        </div>
        <div>
          <dt className="text-muted">Embedding calls</dt>
          <dd className="text-lg font-semibold tabular-nums">{metrics.usage_today.embed_calls ?? 0}</dd>
        </div>
        <div>
          <dt className="text-muted">Cached answers</dt>
          <dd className="text-lg font-semibold tabular-nums">{metrics.usage_today.cache_hits ?? 0}</dd>
        </div>
        <div>
          <dt className="text-muted">Database</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {db === null ? "—" : `${mb(db)} of ${mb(metrics.database_limit_bytes)}`}
          </dd>
          {share !== null && share > 0.8 ? (
            <dd className="flex items-center gap-1 text-xs text-warning">
              <CircleAlert size={12} aria-hidden="true" /> Over 80% of the free plan
            </dd>
          ) : null}
        </div>
      </dl>
      <p className="mt-3 text-xs text-muted">Redis commands are shown in the Upstash console.</p>
    </Card>
  );
}

function Attention({
  review,
  pending,
  metrics,
}: {
  review: ReviewItem[];
  pending: Approval[];
  metrics: Metrics | null;
}) {
  const today = todayIso();
  const items = [
    ...review.map((r) => ({
      key: `r-${r.id}`,
      icon: r.expired ? CircleAlert : Clock,
      tone: r.expired ? "text-danger" : "text-warning",
      text: r.title,
      detail: <Expiry iso={r.expires_at} today={today} />,
      href: r.kind === "kb" ? `/admin/content/kb/${r.id}` : "/admin/content?tab=documents",
    })),
    ...pending.map((a) => ({
      key: `p-${a.id}`,
      icon: Clock,
      tone: "text-warning",
      text: a.title,
      detail: <span className="text-muted">Waiting for approval</span>,
      href: "/admin/approvals",
    })),
    ...(metrics?.recent_thumbs_down ?? []).map((d) => ({
      key: `d-${d.message_id}`,
      icon: ThumbsDown,
      tone: "text-danger",
      text: d.answer.slice(0, 90),
      detail: <span className="text-muted">{d.comment ?? "Thumbs down"}</span>,
      href: null,
    })),
  ];
  return (
    <Card>
      <h2 className="mb-3 text-sm font-semibold">Needs attention</h2>
      {metrics && metrics.open_unanswered > 0 ? (
        <Link href="/admin/unanswered" className="mb-3 flex items-center gap-2 text-sm text-accent">
          <MessageCircleQuestion size={16} aria-hidden="true" />
          {metrics.open_unanswered} unanswered question{metrics.open_unanswered === 1 ? "" : "s"}
        </Link>
      ) : null}
      {items.length === 0 ? (
        <p className="text-sm text-muted">Nothing needs attention. Everything is in date.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {items.slice(0, 12).map(({ key, icon: Icon, tone, text, detail, href }) => (
            <li key={key} className="flex items-start gap-3 py-2 text-sm">
              <Icon size={16} className={`mt-0.5 shrink-0 ${tone}`} aria-hidden="true" />
              <div className="min-w-0">
                {href ? (
                  <Link href={href} className="block truncate hover:text-accent">
                    {text}
                  </Link>
                ) : (
                  <p className="truncate">{text}</p>
                )}
                <div className="text-xs">{detail}</div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** Dashboard (DESIGN.md 6.2.2, ADM-3). Metrics are admin only; staff see their reminders. */
export default function DashboardPage() {
  const { can } = useAdmin();
  const admin = can("view_metrics");
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [review, setReview] = useState<ReviewItem[] | null>(null);
  const [pending, setPending] = useState<Approval[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      admin ? adminApi.metrics() : Promise.resolve(null),
      adminApi.review(!admin),
      adminApi.approvals(),
    ])
      .then(([m, r, p]) => {
        setMetrics(m);
        setReview(r);
        setPending(p);
      })
      .catch((e: Error) => setError(e.message));
  }, [admin]);

  if (error) return <Notice tone="error">{error}</Notice>;
  if (!review) return <Loading />;

  return (
    <>
      <PageHeader title="Dashboard" />
      {metrics ? (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Kpi label="Questions today" value={String(metrics.questions_today)} />
            <Kpi label="Fallback rate" value={percent(metrics.fallback_rate)} note={`last ${metrics.window_days} days`} />
            <Kpi
              label="Avg response time"
              value={metrics.avg_latency_ms === null ? "—" : `${(metrics.avg_latency_ms / 1000).toFixed(1)} s`}
              note={`last ${metrics.window_days} days`}
            />
            <Kpi label="Thumbs up" value={percent(metrics.thumbs_up_rate)} note={`${metrics.thumbs_down} thumbs down`} />
          </div>
          <Usage metrics={metrics} />
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-2">
              <DailyBars
                title={`Questions per day, last ${metrics.window_days} days`}
                points={metrics.days.map((d) => ({ day: d.day, value: d.questions }))}
              />
            </Card>
            <Card>
              <CategoryBars title="Answers by source" items={metrics.tool_usage} />
            </Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <h2 className="mb-2 text-sm font-semibold">Top 10 questions</h2>
              <Table label="Top 10 questions" head={["Question", "Times asked"]}>
                {metrics.top_questions.length === 0 ? (
                  <tr className={ROW}>
                    <td className={`${CELL} text-muted`} colSpan={2}>
                      No questions yet.
                    </td>
                  </tr>
                ) : (
                  metrics.top_questions.map((q) => (
                    <tr key={q.label} className={ROW}>
                      <td className={CELL}>{q.label}</td>
                      <td className={`${CELL} tabular-nums`}>{q.count}</td>
                    </tr>
                  ))
                )}
              </Table>
            </div>
            <Attention review={review} pending={pending} metrics={metrics} />
          </div>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Attention review={review} pending={pending} metrics={null} />
          <Card>
            <h2 className="mb-2 text-sm font-semibold">Your content</h2>
            <p className="mb-3 text-sm text-muted">
              Add or update answers for your office. An admin approves them before the chat uses them.
            </p>
            <Link href="/admin/content/kb/new" className="text-sm font-semibold text-accent">
              Add a knowledge entry
            </Link>
          </Card>
        </div>
      )}
    </>
  );
}
