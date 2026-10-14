"use client";

import { NO_DATA_FILL, type RangeLegendStop } from "@/lib/mapLicenceCredits";

/** off = nothing drawn (no bands); zoom-hint = layer active but colours not at this zoom. */
export type MapRangeLegendMode = "off" | "zoom-hint" | "bands";

export type MapRangeLegendProps = {
  title: string;
  /** Optional one-line explanation under the title. */
  blurb?: string;
  ranges: RangeLegendStop[];
  /** When true, show the hatched/grey no-data swatch (bands mode only). */
  showNoData?: boolean;
  /**
   * off — no bands (nothing drawn for this layer).
   * zoom-hint — show zoomHint instead of bands.
   * bands — show colour stops + optional source.
   */
  mode?: MapRangeLegendMode;
  /** Shown in zoom-hint mode (e.g. "Zoom in to see colours"). */
  zoomHint?: string;
  /** Source / licence line under the bands. */
  source?: string | null;
  className?: string;
};

/**
 * Range legend for map colour ramps. Labels are ranges (or opaque bands for
 * withheld rent metrics) — never a single published rent £ figure.
 * Follows the active layer only: no bands when nothing is drawn; zoom hint
 * when the layer is active but colours are not drawn at this zoom.
 */
export default function MapRangeLegend({
  title,
  blurb,
  ranges,
  showNoData = true,
  mode = "bands",
  zoomHint = "Zoom in to see colours",
  source = null,
  className,
}: MapRangeLegendProps) {
  // No active colour layer → hide the whole control (no bands).
  if (mode === "off") return null;

  const showBands = mode === "bands" && ranges.length > 0;
  const showHint = mode === "zoom-hint";

  return (
    <div
      className={["map-range-legend", className].filter(Boolean).join(" ")}
      data-testid="map-range-legend"
      aria-label={title}
      data-mode={mode}
    >
      <p className="map-range-legend-title" data-testid="map-range-legend-title">
        {title}
      </p>
      {blurb ? (
        <p className="map-range-legend-blurb" data-testid="map-range-legend-blurb">
          {blurb}
        </p>
      ) : null}
      {showHint ? (
        <p
          className="map-range-legend-zoom-hint"
          data-testid="map-range-legend-zoom-hint"
        >
          {zoomHint}
        </p>
      ) : null}
      {showBands ? (
        <ul className="map-range-legend-list" data-testid="map-range-legend-bands">
          {ranges.map((row) => (
            <li key={`${row.from}-${row.to}-${row.color}`}>
              <span
                className="map-range-legend-swatch"
                style={{ background: row.color }}
                aria-hidden
              />
              <span data-testid="map-range-legend-text">
                {row.from}
                {row.to === "and above" ? " and above" : `–${row.to}`}
              </span>
            </li>
          ))}
          {showNoData ? (
            <li data-testid="map-range-legend-no-data">
              <span
                className="map-range-legend-swatch map-range-legend-swatch-nodata"
                style={{ backgroundColor: NO_DATA_FILL }}
                aria-hidden
              />
              <span>No data</span>
            </li>
          ) : null}
        </ul>
      ) : null}
      {showBands && source ? (
        <p className="map-range-legend-source" data-testid="map-range-legend-source">
          {source}
        </p>
      ) : null}
    </div>
  );
}
