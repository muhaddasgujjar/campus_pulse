"use client";

import { use, useState } from "react";

import { DocumentsTab } from "@/components/admin/DocumentsTab";
import { KnowledgeTab } from "@/components/admin/KnowledgeTab";
import { StructuredTab } from "@/components/admin/StructuredTab";
import { PageHeader } from "@/components/admin/ui";
import type { TableName } from "@/lib/admin/api";
import { TABLE_SPECS } from "@/lib/admin/tables";

type Tab = "knowledge" | "documents" | TableName;

const TABS: { id: Tab; label: string }[] = [
  { id: "knowledge", label: "Knowledge" },
  { id: "documents", label: "Documents" },
  ...(Object.values(TABLE_SPECS).map((s) => ({ id: s.name, label: s.label })) as { id: Tab; label: string }[]),
];

/** Content list (DESIGN.md 6.2.3): one tab per kind of verified data. */
export default function ContentPage(props: PageProps<"/admin/content">) {
  const wanted = use(props.searchParams).tab;
  const [tab, setTab] = useState<Tab>(() =>
    TABS.some((t) => t.id === wanted) ? (wanted as Tab) : "knowledge",
  );

  function pick(next: Tab) {
    setTab(next);
    window.history.replaceState(null, "", `?tab=${next}`);
  }

  return (
    <>
      <PageHeader title="Content" />
      <div role="tablist" aria-label="Content type" className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls="content-panel"
            onClick={() => pick(t.id)}
            className={`min-h-11 shrink-0 border-b-2 px-4 text-sm ${
              tab === t.id ? "border-primary font-semibold text-accent" : "border-transparent text-muted hover:text-text"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id="content-panel" aria-labelledby={`tab-${tab}`}>
        {tab === "knowledge" ? (
          <KnowledgeTab />
        ) : tab === "documents" ? (
          <DocumentsTab />
        ) : (
          <StructuredTab key={tab} spec={TABLE_SPECS[tab]} />
        )}
      </div>
    </>
  );
}
