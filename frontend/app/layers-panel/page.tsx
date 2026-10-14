"use client";

import { useState } from "react";

import LayersPanel, { type LayerToggleState } from "@/components/LayersPanel";

/**
 * Dev/QA preview for the catalog-driven LayersPanel.
 * Public map HUD uses the Annual Ground Rent breakdown (/ledger-panel).
 */
export default function LayersPanelPreviewPage() {
  const [enabled, setEnabled] = useState<LayerToggleState>({});

  return (
    <main className="layers-panel-page">
      <div className="layers-panel-page-inner">
        <h1 className="layers-panel-page-brand">Scot-LAND</h1>
        <p className="layers-panel-page-lead">
          Catalog layers preview (Dev/QA) — driven by{" "}
          <code>/layers/catalog</code>. Public HUD:{" "}
          <a href="/ledger-panel">Annual Ground Rent breakdown</a>.
        </p>
        <LayersPanel enabled={enabled} onEnabledChange={setEnabled} />
      </div>
    </main>
  );
}
