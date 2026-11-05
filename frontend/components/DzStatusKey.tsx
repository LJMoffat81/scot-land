"use client";

import {
  DZ_STATUS_CATEGORIES,
  DZ_STATUS_CREDIT,
  DZ_STATUS_KEY_TITLE,
  DZ_STATUS_VINTAGE_NOTE,
} from "@/lib/dzStatusLayer";

/**
 * DZ-HEATMAP PR-B key. Exactly: title, the five locked labels, the credit,
 * the vintage note. No other text. Rendered only for a validated payload.
 */
export default function DzStatusKey() {
  return (
    <li className="layers-panel-row" data-testid="dz-status-key">
      <div className="layers-inline-legend">
        <p className="layers-nav-subgroup" data-testid="dz-status-key-title">
          {DZ_STATUS_KEY_TITLE}
        </p>
        <ul className="layer-legend" aria-label={DZ_STATUS_KEY_TITLE}>
          {DZ_STATUS_CATEGORIES.map((cat) => (
            <li key={cat.id} data-testid={`dz-status-key-${cat.id}`}>
              <span
                className="layer-legend-swatch"
                style={{ backgroundColor: cat.color }}
              />
              <span>{cat.label}</span>
            </li>
          ))}
        </ul>
        <p
          className="layer-meta layers-source-caption"
          data-testid="dz-status-key-credit"
        >
          {DZ_STATUS_CREDIT}
        </p>
        <p className="layer-meta" data-testid="dz-status-key-vintage">
          {DZ_STATUS_VINTAGE_NOTE}
        </p>
      </div>
    </li>
  );
}
