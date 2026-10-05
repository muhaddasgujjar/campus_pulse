type BrandMarkProps = {
  size?: number;
  glow?: boolean;
  className?: string;
};

/**
 * Brand mark: teal graduation cap inside a white circle with a soft teal glow (DESIGN.md 2.4).
 * Decorative by default; pass a visible label next to it for screen readers.
 */
export function BrandMark({ size = 40, glow = false, className = "" }: BrandMarkProps) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-(--radius-pill) bg-mark-bg text-mark-fg ${glow ? "shadow-(--glow-teal)" : ""} ${className}`}
      style={{ width: size, height: size }}
    >
      <svg
        viewBox="0 0 24 24"
        width={size * 0.6}
        height={size * 0.6}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M2 9.5 12 5l10 4.5-10 4.5L2 9.5Z" />
        <path d="M6 11.3v4.2c0 1.4 2.7 2.8 6 2.8s6-1.4 6-2.8v-4.2" />
        <path d="M22 9.5v5" />
      </svg>
    </span>
  );
}
