"use client";

import { useState } from "react";

import { formatDate } from "@/lib/chat/format";

/*
 * Dashboard charts (DESIGN.md 6.2.2). One series each, so one hue (--chart-1, validated
 * against both surfaces) and no legend: the title names the series. Thin bars with 4px rounded
 * data-ends on the baseline, 2px gaps, recessive grid, a tooltip on hover and keyboard focus,
 * and a table view for screen readers.
 */

function niceMax(value: number): number {
  if (value <= 4) return 4;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const step = [1, 2, 2.5, 5, 10].find((s) => s * magnitude * 4 >= value) ?? 10;
  return step * magnitude * 4;
}

export function DailyBars({
  title,
  points,
}: {
  title: string;
  points: { day: string; value: number }[];
}) {
  const [active, setActive] = useState<number | null>(null);
  const width = 640;
  const height = 200;
  const pad = { top: 12, right: 8, bottom: 28, left: 32 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const max = niceMax(Math.max(0, ...points.map((p) => p.value)));
  const slot = plotW / Math.max(points.length, 1);
  const barW = Math.max(4, Math.min(24, slot - 2));
  const ticks = [0, max / 2, max];
  const y = (v: number) => pad.top + plotH - (v / max) * plotH;
  const shown = active !== null ? points[active] : null;

  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-semibold">{title}</figcaption>
      <div className="relative">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-auto w-full" role="img" aria-label={title}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
              <text x={pad.left - 6} y={y(t) + 4} textAnchor="end" fontSize={11} fill="var(--text-muted)">
                {t}
              </text>
            </g>
          ))}
          {points.map((p, i) => {
            const x = pad.left + i * slot + (slot - barW) / 2;
            const h = Math.max(p.value > 0 ? 2 : 0, (p.value / max) * plotH);
            const top = pad.top + plotH - h;
            const r = Math.min(4, barW / 2, h);
            const label = `${formatDate(p.day)}: ${p.value}`;
            return (
              <g
                key={p.day}
                tabIndex={0}
                aria-label={label}
                onMouseEnter={() => setActive(i)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(i)}
                onBlur={() => setActive(null)}
                className="outline-none"
              >
                {/* hit target larger than the mark */}
                <rect x={pad.left + i * slot} y={pad.top} width={slot} height={plotH} fill="transparent" />
                {h > 0 ? (
                  <path
                    d={`M${x},${pad.top + plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${pad.top + plotH} Z`}
                    fill="var(--chart-1)"
                    opacity={active === null || active === i ? 1 : 0.55}
                  />
                ) : null}
                {i % Math.ceil(points.length / 7) === 0 || i === points.length - 1 ? (
                  <text x={x + barW / 2} y={height - 8} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
                    {new Date(p.day).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
        {shown ? (
          <div
            role="status"
            className="pointer-events-none absolute top-0 right-0 rounded-(--radius-sm) border border-border bg-surface-2 px-3 py-1.5 text-xs"
          >
            <span className="text-muted">{formatDate(shown.day)}</span>{" "}
            <span className="font-semibold">{shown.value}</span>
          </div>
        ) : null}
      </div>
      <table className="sr-only">
        <caption>{title}</caption>
        <tbody>
          {points.map((p) => (
            <tr key={p.day}>
              <th scope="row">{formatDate(p.day)}</th>
              <td>{p.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

/** Horizontal bars for a few categories, each labeled with its name and value in text ink. */
export function CategoryBars({ title, items }: { title: string; items: { label: string; count: number }[] }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="text-sm font-semibold">{title}</figcaption>
      {items.length === 0 ? (
        <p className="text-sm text-muted">No answers in this period yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.label} className="grid grid-cols-[8rem_1fr_3rem] items-center gap-3 text-sm" title={`${item.label}: ${item.count}`}>
              <span className="truncate text-muted">{item.label.replaceAll("_", " ")}</span>
              <span className="h-2.5 rounded-e-[4px] bg-chart-1" style={{ width: `${(item.count / max) * 100}%` }} />
              <span className="text-end tabular-nums">{item.count}</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
