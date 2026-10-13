"use client";

import { useState } from "react";

import LedgerPanel from "@/components/LedgerPanel";
import type { LedgerToggleState } from "@/lib/ledger";

/**
 * Isolated preview for the Natural capital ledger panel.
 * Public map HUD uses the same component (Ledger button).
 */
export default function LedgerPanelPreviewPage() {
  const [enabled, setEnabled] = useState<LedgerToggleState>({});

  return (
    <main className="ledger-panel-page">
      <div className="ledger-panel-page-inner">
        <h1 className="ledger-panel-page-brand">Scot-LAND</h1>
        <p className="ledger-panel-page-lead">
          Natural capital ledger preview — driven by{" "}
          <code>/ledger</code> (fixture fallback). Open via Ledger on the main
          map. Catalog GIS checklist lives on{" "}
          <a href="/layers-panel">/layers-panel</a> (Dev/QA only).
        </p>
        <LedgerPanel enabled={enabled} onEnabledChange={setEnabled} />
      </div>
    </main>
  );
}
