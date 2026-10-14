/**
 * Map choropleth colour ramps and public-context legend helpers.
 * AGR / rent / fiscal £ ramps are removed from the public shell.
 */

export type MetricId =
  | "house_price"
  | "land_share"
  | "simd"
  | "pop_density";

export type MetricDef = {
  id: MetricId;
  property: string;
  label: string;
  group: "value" | "context";
  /** Unit for legend titles; stop labels stay numeric (or £ for house prices). */
  unit?: string;
  stops: [number, string][];
};

/** Public-safe colour ramps only (no forbidden AGR £ properties). */
export const METRICS: MetricDef[] = [
  {
    id: "house_price",
    property: "average_price_gbp",
    label: "House prices",
    group: "value",
    unit: "£",
    stops: [
      [100000, "#fff5f0"],
      [140000, "#fcbba1"],
      [180000, "#fc9272"],
      [220000, "#ef3b2c"],
      [280000, "#a50f15"],
    ],
  },
  {
    id: "land_share",
    property: "site_share_pct",
    label: "Land share %",
    group: "value",
    unit: "%",
    stops: [
      [30, "#f7fcfd"],
      [45, "#ccece6"],
      [55, "#66c2a4"],
      [65, "#238b45"],
      [75, "#00441b"],
    ],
  },
  {
    id: "simd",
    property: "simd_pct_20most_deprived",
    label: "Deprivation",
    group: "context",
    unit: "% in 20% most deprived",
    stops: [
      [0, "#ffffd4"],
      [8, "#fed98e"],
      [16, "#fe9929"],
      [28, "#d95f0e"],
      [40, "#993404"],
    ],
  },
  {
    id: "pop_density",
    property: "population_density_per_km2",
    label: "People per square kilometre",
    group: "context",
    unit: "people/km²",
    stops: [
      [10, "#f7fcf0"],
      [100, "#ccebc5"],
      [500, "#7bccc4"],
      [1500, "#2b8cbe"],
      [3000, "#084081"],
    ],
  },
];

/** Public shell may show these context ramps (never AGR / rent £ choropleth). */
export const PUBLIC_CONTEXT_METRIC_IDS: readonly MetricId[] = [
  "pop_density",
  "simd",
  "house_price",
  "land_share",
] as const;

/** Default public reference ramp while council choropleth paint stays off. */
export const DEFAULT_PUBLIC_CONTEXT_METRIC_ID: MetricId = "pop_density";

export function metricById(
  id: MetricId | string | undefined | null,
): MetricDef | undefined {
  if (!id) return undefined;
  return METRICS.find((m) => m.id === id);
}

export function publicContextMetric(
  id: MetricId | string | undefined | null = DEFAULT_PUBLIC_CONTEXT_METRIC_ID,
): MetricDef {
  const wanted =
    id && PUBLIC_CONTEXT_METRIC_IDS.includes(id as MetricId)
      ? id
      : DEFAULT_PUBLIC_CONTEXT_METRIC_ID;
  return (
    metricById(wanted) ??
    METRICS.find((m) => m.id === DEFAULT_PUBLIC_CONTEXT_METRIC_ID)!
  );
}

/** Legend title: metric label plus unit when present (unit not repeated on each stop). */
export function rangeLegendTitle(metric: MetricDef): string {
  const base =
    metric.id === "pop_density"
      ? "Population density (range)"
      : `${metric.label} (range)`;
  if (!metric.unit || metric.unit === "£" || metric.unit.startsWith("£")) {
    return base;
  }
  if (metric.unit === "%") return base;
  return `${base} — ${metric.unit}`;
}

/**
 * Metric used for council-fill / no-data hatch paint expressions.
 * Public shell keeps choropleth off; still bind paint to a public context ramp
 * so hidden layers never retain an AGR £ expression.
 */
export function paintMetricForChoropleth(
  choropleth: MetricId | "off",
): MetricDef {
  if (choropleth === "off") return publicContextMetric();
  return metricById(choropleth) ?? publicContextMetric();
}
