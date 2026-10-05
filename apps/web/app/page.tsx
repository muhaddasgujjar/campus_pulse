import Link from "next/link";

import { BrandMark } from "@/components/brand/BrandMark";
import { institution } from "@/lib/institution";

/** Welcome screen (DESIGN.md 6.1). M1 placeholder: brand, tagline, Start chat. */
export default function WelcomePage() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-xl flex-col items-center justify-center gap-8 px-6 text-center">
      <BrandMark size={96} glow />
      <div className="flex flex-col gap-3">
        <h1 className="text-[32px] leading-tight font-bold">{institution.productName}</h1>
        <p className="text-lg text-muted">{institution.greeting}</p>
      </div>
      <Link
        href="/chat"
        className="inline-flex min-h-11 items-center justify-center rounded-(--radius-pill) bg-primary px-8 font-semibold text-on-primary transition-colors duration-(--duration-fast) hover:bg-primary-hover"
      >
        Start chat
      </Link>
      <p className="text-xs text-muted">{institution.name}</p>
    </main>
  );
}
