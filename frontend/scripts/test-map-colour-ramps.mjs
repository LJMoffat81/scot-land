/**
 * Node asserts for public colour ramps (no AGR £ scales).
 * Mirrors mapColourRamps / mapLicenceCredits legend helpers.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const PUBLIC_CONTEXT_METRIC_IDS = [
  "pop_density",
  "simd",
  "house_price",
  "land_share",
];

const DEFAULT_PUBLIC_CONTEXT_METRIC_ID = "pop_density";

const FORBIDDEN_AGR_METRIC_IDS = [
  "agr_plot",
  "rent_per_sqm",
  "agr_price_pct",
  "site_capital",
  "gross_liability",
  "net_contribution",
  "vacant_residual",
];

const METRICS = [
  {
    id: "pop_density",
    property: "population_density_per_km2",
    label: "People per square kilometre",
    unit: "people/km²",
    stops: [
      [10, "#c6dbef"],
      [100, "#6baed6"],
      [500, "#2171b5"],
      [1500, "#08519c"],
      [3000, "#08306b"],
    ],
  },
  {
    id: "simd",
    property: "simd_pct_20most_deprived",
    label: "Deprivation",
    unit: "% in 20% most deprived",
    stops: [
      [0, "#ffffd4"],
      [8, "#fed98e"],
      [40, "#993404"],
    ],
  },
  {
    id: "house_price",
    property: "average_price_gbp",
    label: "House prices",
    unit: "£",
    stops: [
      [100000, "#fff5f0"],
      [180000, "#fc9272"],
      [280000, "#a50f15"],
    ],
  },
  {
    id: "land_share",
    property: "site_share_pct",
    label: "Land share %",
    unit: "%",
    stops: [
      [30, "#f7fcfd"],
      [55, "#66c2a4"],
      [75, "#00441b"],
    ],
  },
];

function formatStopValue(value, unit) {
  const n = Number.isFinite(value) ? value : 0;
  const formatted =
    Math.abs(n) >= 1000
      ? n.toLocaleString("en-GB", { maximumFractionDigits: 0 })
      : String(n);
  if (unit === "£" || unit?.startsWith("£")) return `£${formatted}`;
  return formatted;
}

function rangeLegendFromStops(stops, opts = {}) {
  const ranges = stops.map(([value, color], i) => {
    const next = stops[i + 1];
    const from = formatStopValue(value, opts.unit);
    const to = next ? formatStopValue(next[0], opts.unit) : "and above";
    return { from, to, color };
  });
  return { ranges, noData: { label: "No data", color: "#bdbdbd" } };
}

function publicContextMetric(id = DEFAULT_PUBLIC_CONTEXT_METRIC_ID) {
  const wanted = PUBLIC_CONTEXT_METRIC_IDS.includes(id)
    ? id
    : DEFAULT_PUBLIC_CONTEXT_METRIC_ID;
  return METRICS.find((m) => m.id === wanted);
}

function paintMetricForChoropleth(choropleth) {
  if (choropleth === "off") return publicContextMetric();
  return METRICS.find((m) => m.id === choropleth) ?? publicContextMetric();
}

// Public context ramps keep numeric / house-price £ labels — never rent bands.
for (const id of PUBLIC_CONTEXT_METRIC_IDS) {
  const metric = publicContextMetric(id);
  assert.ok(metric, id);
  const legend = rangeLegendFromStops(metric.stops, {
    metricId: metric.id,
    unit: metric.unit,
  });
  assert.equal(legend.ranges[0].from.startsWith("Band"), false, id);
  assert.doesNotMatch(JSON.stringify(legend), /Band /, id);
  if (id !== "house_price") {
    assert.doesNotMatch(JSON.stringify(legend), /£\d/, id);
  }
  assert.equal(legend.noData.color, "#bdbdbd");
}

const houseLegend = rangeLegendFromStops(
  publicContextMetric("house_price").stops,
  {
    metricId: "house_price",
    unit: "£",
  },
);
assert.match(houseLegend.ranges[0].from, /^£/);

// Hidden choropleth must bind to public density, never AGR paint default.
const paintOff = paintMetricForChoropleth("off");
assert.equal(paintOff.id, "pop_density");
assert.equal(paintOff.property, "population_density_per_km2");

// Source file must not keep the seven removed AGR colour scales.
const here = dirname(fileURLToPath(import.meta.url));
const rampSource = readFileSync(
  join(here, "../lib/mapColourRamps.ts"),
  "utf8",
);
for (const id of FORBIDDEN_AGR_METRIC_IDS) {
  assert.equal(
    rampSource.includes(`id: "${id}"`),
    false,
    `mapColourRamps must not define ${id}`,
  );
}

console.log("test-map-colour-ramps: ok");
