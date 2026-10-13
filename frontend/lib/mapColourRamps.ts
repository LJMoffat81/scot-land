/**
 * Map choropleth colour ramps and public-context legend helpers.
 * Rent / AGR / fiscal metrics stay band-labelled (no public rent £).
 */

export type MetricId =
  | "agr_plot"
  | "rent_per_sqm"
  | "house_price"
  | "agr_price_pct"
  | "land_share"
  | "site_capital"
  | "simd"
  | "pop_density"
  | "net_contribution"
  | "gross_liability"
  | "vacant_residual";

export type MetricDef = {
  id: MetricId;
  property: string;
  label: string;
  group: "value" | "context" | "fiscal";
  /** Unit for legend titles; stop labels stay numeric (or £ for house prices). */
  unit?: string;
  stops: [number, string][];
};

/** Colour ramps tuned to each metric’s typical Scotland range. */
export const METRICS: MetricDef[] = [
  {
    id: "agr_plot",
    property: "annual_ground_rent_plot_gbp",
    label: "Typical plot rent",
    group: "value",
    unit: "£",
    stops: [
      [0, "#ffffcc"],
      [500, "#c7e9b4"],
      [1500, "#7fcdbb"],
      [3000, "#41b6c4"],
      [4500, "#2c7fb8"],
      [6500, "#253494"],
    ],
  },
  {
    id: "rent_per_sqm",
    property: "site_rental_per_sqm_gbp",
    label: "Rent per square metre",
    group: "value",
    unit: "£/m²",
    stops: [
      [0, "#f7fcf5"],
      [5, "#c7e9c0"],
      [12, "#74c476"],
      [20, "#31a354"],
      [30, "#006d2c"],
    ],
  },
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
    id: "agr_price_pct",
    property: "agr_as_pct_of_price",
    label: "Rent as a share of price",
    group: "value",
    unit: "%",
    stops: [
      [0.5, "#f7fbff"],
      [1.5, "#c6dbef"],
      [2.5, "#6baed6"],
      [3.5, "#2171b5"],
      [5, "#08306b"],
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
    id: "site_capital",
    property: "site_capital_per_sqm_gbp",
    label: "Land value per square metre",
    group: "value",
    unit: "£/m²",
    stops: [
      [50, "#fcfbfd"],
      [150, "#dadaeb"],
      [300, "#9e9ac8"],
      [450, "#6a51a3"],
      [600, "#3f007d"],
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
  {
    id: "gross_liability",
    property: "gross_plot_liability_gbp",
    label: "Annual Ground Rent",
    group: "fiscal",
    unit: "£",
    stops: [
      [0, "#ffffcc"],
      [1500, "#c7e9b4"],
      [3500, "#41b6c4"],
      [5500, "#2c7fb8"],
      [8000, "#253494"],
    ],
  },
  {
    id: "net_contribution",
    property: "net_contribution_plot_gbp",
    label: "Against one person's share",
    group: "fiscal",
    unit: "£",
    // Teal is below one person's share. Orange is above it.
    stops: [
      [-18000, "#01665e"],
      [-5000, "#80cdc1"],
      [0, "#f5f5f5"],
      [2000, "#fdb863"],
      [6000, "#b35806"],
    ],
  },
  {
    id: "vacant_residual",
    property: "vacant_full_agr_gbp",
    label: "Vacant land",
    group: "context",
    unit: "£",
    stops: [
      [0, "#fff5eb"],
      [2_000_000, "#fdd0a2"],
      [8_000_000, "#fd8d3c"],
      [20_000_000, "#e6550d"],
      [40_000_000, "#a63603"],
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

export function metricById(id: MetricId | string | undefined | null): MetricDef | undefined {
  if (!id) return undefined;
  return METRICS.find((m) => m.id === id);
}

export function publicContextMetric(
  id: MetricId | string | undefined | null = DEFAULT_PUBLIC_CONTEXT_METRIC_ID,
): MetricDef {
  const wanted = id && PUBLIC_CONTEXT_METRIC_IDS.includes(id as MetricId) ? id : DEFAULT_PUBLIC_CONTEXT_METRIC_ID;
  return metricById(wanted) ?? METRICS.find((m) => m.id === DEFAULT_PUBLIC_CONTEXT_METRIC_ID)!;
}

/** Legend title: metric label plus unit when present (unit not repeated on each stop). */
export function rangeLegendTitle(metric: MetricDef): string {
  const base = metric.id === "pop_density" ? "Population density (range)" : `${metric.label} (range)`;
  if (!metric.unit || metric.unit === "£" || metric.unit.startsWith("£")) return base;
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
