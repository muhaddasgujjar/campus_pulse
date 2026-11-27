import { Mail, Phone } from "lucide-react";

import type { Office } from "@/lib/chat/protocol";

type FallbackCardProps = {
  office: Office | null;
  onTellUs?: () => void;
};

/**
 * "I don't have verified information on this." with the office to contact: tap-to-call
 * phones and email (DESIGN.md Section 4, ANS-5). Shown instead of a guessed answer.
 */
export function FallbackCard({ office, onTellUs }: FallbackCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-(--radius-md) border border-border-teal bg-surface-teal p-4">
      <p className="font-medium">I don&apos;t have verified information on this.</p>
      {office?.name && (
        <div className="flex flex-col gap-2 text-sm">
          <p>
            <span className="text-muted">The {office.name} can help</span>
            {office.hours && <span className="text-muted"> · {office.hours}</span>}
          </p>
          <div className="flex flex-wrap gap-2">
            {office.phones.map((phone) => (
              <a
                key={phone}
                href={`tel:${phone.split("-").slice(0, 2).join("")}`}
                aria-label={`Call ${phone}`}
                className="inline-flex min-h-11 items-center gap-2 rounded-(--radius-pill) bg-primary px-4 font-semibold text-on-primary hover:bg-primary-hover"
              >
                <Phone size={16} strokeWidth={1.75} aria-hidden="true" />
                {phone}
              </a>
            ))}
            {office.email && (
              <a
                href={`mailto:${office.email}`}
                aria-label={`Email ${office.email}`}
                className="inline-flex min-h-11 items-center gap-2 rounded-(--radius-pill) border border-border-teal px-4 text-accent hover:bg-surface-2"
              >
                <Mail size={16} strokeWidth={1.75} aria-hidden="true" />
                {office.email}
              </a>
            )}
          </div>
        </div>
      )}
      {onTellUs && (
        <button
          type="button"
          onClick={onTellUs}
          className="self-start text-sm text-accent underline underline-offset-2"
        >
          Tell us what you were looking for
        </button>
      )}
    </div>
  );
}
