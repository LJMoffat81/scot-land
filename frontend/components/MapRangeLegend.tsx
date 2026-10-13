"use client";

import { NO_DATA_FILL, type RangeLegendStop } from "@/lib/mapLicenceCredits";

export type MapRangeLegendProps = {
  title: string;
  ranges: RangeLegendStop[];
  /** When true, show the hatched/grey no-data swatch. */
  showNoData?: boolean;
  className?: string;
};

/**
 * Range legend for map colour ramps. Labels are ranges (or opaque bands for
 * withheld rent metrics) — never a single published rent £ figure.
 */
export default function MapRangeLegend({
  title,
  ranges,
  showNoData = true,
  className,
}: MapRangeLegendProps) {
  if (ranges.length === 0 && !showNoData) return null;

  return (
    <div
      className={["map-range-legend", className].filter(Boolean).join(" ")}
      data-testid="map-range-legend"
      aria-label={title}
    >
      <p className="map-range-legend-title">{title}</p>
      <ul className="map-range-legend-list">
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
              style={{ background: NO_DATA_FILL }}
              aria-hidden
            />
            <span>No data</span>
          </li>
        ) : null}
      </ul>
    </div>
  );
}
