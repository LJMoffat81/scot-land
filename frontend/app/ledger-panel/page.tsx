"use client";

import { useState } from "react";

import LedgerPanel from "@/components/LedgerPanel";
import type { LedgerToggleState } from "@/lib/ledger";

/**
 * Isolated preview for the Annual Ground Rent breakdown panel.
 * Public map HUD uses the same component (Layers button).
 */
export default function LedgerPanelPreviewPage() {
  const [enabled, setEnabled] = useState<LedgerToggleState>({});

  return (
    <main className="ledger-panel-page">
      <div className="ledger-panel-page-inner">
        <h1 className="ledger-panel-page-brand">Scot-LAND</h1>
        <p className="ledger-panel-page-lead">
          Annual Ground Rent breakdown preview — driven by{" "}
          <code>/ledger</code> (sample data if the live feed is offline). Open
          via Layers on the main map. Catalog GIS checklist lives on{" "}
          <a href="/layers-panel">/layers-panel</a> (Dev/QA only).
        </p>
        <LedgerPanel enabled={enabled} onEnabledChange={setEnabled} />
      </div>
    </main>
  );
}
