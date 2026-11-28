import type { Metadata } from "next";

import { AdminShell } from "@/components/admin/AdminShell";
import { institution } from "@/lib/institution";

export const metadata: Metadata = { title: `Admin · ${institution.productName}` };

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
