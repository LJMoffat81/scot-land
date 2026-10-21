/**
 * Map choropleth colour ramps and public-context legend helpers.
 * AGR / rent / fiscal £ ramps are removed from the public shell.
 */

/** Choropleth fill alpha so basemap labels stay readable (BASEMAP-SHOWTHRU-1). */
export const CHOROPLETH_FILL_OPACITY = 0.55;

/** No-data hatch fill alpha (same pin as choropleth fill). */
export const NODATA_HATCH_OPACITY = 0.55;

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

/** Exact visitor title for the population-density range legend (SW-022). */
export const POP_DENSITY_LEGEND_TITLE =
  "Population density — people per km²";

/**
 * Default-view (council fill) people/km² legend title.
 * Single source for map chip, Layers key row, and e2e (FRONTEND-BATCH-4).
 */
export const POP_DENSITY_RANGE_LEGEND_TITLE =
  "People per square kilometre (people/km²)";

/** One-line blurb under the density title (SW-022). */
export const POP_DENSITY_LEGEND_BLURB =
  "Busier places tend to have a higher Annual Ground Rent.";

/** Source / licence line under density bands (SW-022). */
export const POP_DENSITY_LEGEND_SOURCE =
  "Source: National Records of Scotland mid-year estimates, Open Government Licence v3.0";

/** Shown instead of bands when density colours are not drawn at this zoom. */
export const POP_DENSITY_ZOOM_HINT = "Zoom in to see colours";

/**
 * Zoom at which Data Zone / density context colours become drawable.
 * Keep in sync with DATA_ZONE_MIN_ZOOM in ScotlandMap.
 */
export const POP_DENSITY_COLOURS_MIN_ZOOM = 10;

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
    // Stronger, clearly distinct blues (SW-022); adjacent stops pass contrast checks.
    stops: [
      [10, "#c6dbef"],
      [100, "#6baed6"],
      [500, "#2171b5"],
      [1500, "#08519c"],
      [3000, "#08306b"],
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

/** FRONTEND-BATCH-1 default view; never a £ metric. */
export const DEFAULT_VIEW_METRIC_ID: MetricId = DEFAULT_PUBLIC_CONTEXT_METRIC_ID;

export function metricById(
  id: MetricId | string | undefined | null,
): MetricDef | undefined {
  if (!id) return undefined;
  return METRICS.find((m) => m.id === id);
}

/** Module-level guard: default view must never be a £ metric (tests import this). */
export const DEFAULT_VIEW_METRIC_IS_NON_GBP =
  metricById(DEFAULT_VIEW_METRIC_ID)?.unit !== "£";

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

/**
 * Legend title for the default-view (and any metric) fill.
 * FRONTEND-BATCH-1 / BATCH-4: pop_density → POP_DENSITY_RANGE_LEGEND_TITLE.
 * Older SW-022 title stays in POP_DENSITY_LEGEND_TITLE for buildActiveLegendView.
 */
export function rangeLegendTitle(metric: MetricDef): string {
  if (metric.id === "pop_density") {
    return POP_DENSITY_RANGE_LEGEND_TITLE;
  }
  if (metric.unit && metric.unit !== "£" && !metric.unit.startsWith("£")) {
    if (metric.unit === "%") {
      return `${metric.label} (range)`;
    }
    return `${metric.label} (${metric.unit})`;
  }
  return `${metric.label} (range)`;
}

/**
 * Relative luminance (sRGB, WCAG). Used to keep density swatches distinct.
 */
export function relativeLuminance(hex: string): number {
  const raw = hex.replace("#", "").trim();
  if (raw.length !== 6) return 0;
  const channels = [0, 2, 4].map((i) => {
    const c = parseInt(raw.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

/**
 * Adjacent stop contrast ratio (WCAG). Density ramp must stay clearly distinct.
 */
export function adjacentStopContrast(stops: [number, string][]): number[] {
  const ratios: number[] = [];
  for (let i = 0; i < stops.length - 1; i += 1) {
    const a = relativeLuminance(stops[i][1]);
    const b = relativeLuminance(stops[i + 1][1]);
    const lighter = Math.max(a, b);
    const darker = Math.min(a, b);
    ratios.push((lighter + 0.05) / (darker + 0.05));
  }
  return ratios;
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
