import type { ReactNode } from "react";
import { notFound } from "next/navigation";

import { internalUiEnabled } from "@/lib/internalUi";

/**
 * Gate /tax-scenario-panel. Public builds (no NEXT_PUBLIC_ENABLE_INTERNAL_UI=1)
 * get 404 — same pattern as /ledger-panel.
 */
export default function TaxScenarioPanelLayout({
  children,
}: {
  children: ReactNode;
}) {
  if (!internalUiEnabled()) notFound();
  return children;
}
