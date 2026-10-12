"use client";

import { useState } from "react";

import LayersPanel, { type LayerToggleState } from "@/components/LayersPanel";

/**
 * Isolated preview for the catalog-driven LayersPanel.
 * Not the w3w shell — shell/search/place-card land in sibling PRs.
 */
export default function LayersPanelPreviewPage() {
  const [enabled, setEnabled] = useState<LayerToggleState>({});

  return (
    <main className="layers-panel-page">
      <div className="layers-panel-page-inner">
        <h1 className="layers-panel-page-brand">Scot-LAND</h1>
        <p className="layers-panel-page-lead">
          Layers panel preview — driven by{" "}
          <code>/layers/catalog</code>. Slots into the map shell later.
        </p>
        <LayersPanel enabled={enabled} onEnabledChange={setEnabled} />
      </div>
    </main>
  );
}
