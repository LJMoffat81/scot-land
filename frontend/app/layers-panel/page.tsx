"use client";

import { useState } from "react";

import LayersPanel, { type LayerToggleState } from "@/components/LayersPanel";

/**
 * Isolated preview for the catalog-driven LayersPanel.
 * The same component is embedded in the main map Layers tools panel.
 */
export default function LayersPanelPreviewPage() {
  const [enabled, setEnabled] = useState<LayerToggleState>({});

  return (
    <main className="layers-panel-page">
      <div className="layers-panel-page-inner">
        <h1 className="layers-panel-page-brand">Scot-LAND</h1>
        <p className="layers-panel-page-lead">
          Layers panel preview — driven by{" "}
          <code>/layers/catalog</code>. Also open via Layers on the main map.
        </p>
        <LayersPanel enabled={enabled} onEnabledChange={setEnabled} />
      </div>
    </main>
  );
}
