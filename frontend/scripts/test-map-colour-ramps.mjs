/**
 * Node asserts for public colour ramps + rent-band withholding.
 * Mirrors mapColourRamps / mapLicenceCredits legend helpers.
 */
import assert from "node:assert/strict";

const PUBLIC_CONTEXT_METRIC_IDS = [
  "pop_density",
  "simd",
  "house_price",
  "land_share",
];

const DEFAULT_PUBLIC_CONTEXT_METRIC_ID = "pop_density";

const METRICS = [
  {
    id: "pop_density",
    property: "population_density_per_km2",
    label: "People per square kilometre",
    unit: "people/km²",
    stops: [
      [10, "#f7fcf0"],
      [100, "#ccebc5"],
      [500, "#7bccc4"],
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
  {
    id: "agr_plot",
    property: "annual_ground_rent_plot_gbp",
    label: "Typical plot rent",
    unit: "£",
    stops: [
      [0, "#ffffcc"],
      [500, "#c7e9b4"],
    ],
  },
  {
    id: "vacant_residual",
    property: "vacant_full_agr_gbp",
    label: "Vacant land",
    unit: "£",
    stops: [
      [0, "#fff5eb"],
      [2_000_000, "#fdd0a2"],
    ],
  },
  {
    id: "net_contribution",
    property: "net_contribution_plot_gbp",
    label: "Against one person's share",
    unit: "£",
    stops: [
      [-5000, "#80cdc1"],
      [0, "#f5f5f5"],
    ],
  },
];

function isRentMetricId(metricId) {
  const id = metricId.toLowerCase();
  return (
    id.includes("agr") ||
    id.includes("rent") ||
    id.includes("liability") ||
    id.includes("charge") ||
    id.includes("site_capital") ||
    id.includes("gross_") ||
    id.includes("vacant_residual") ||
    id.includes("net_contribution") ||
    id.endsWith("_gbp")
  );
}

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
  const withholdPounds = isRentMetricId(opts.metricId ?? "");
  const ranges = stops.map(([value, color], i) => {
    const next = stops[i + 1];
    const from = withholdPounds
      ? `Band ${String.fromCharCode(65 + i)}`
      : formatStopValue(value, opts.unit);
    const to = next
      ? withholdPounds
        ? `Band ${String.fromCharCode(65 + i + 1)}`
        : formatStopValue(next[0], opts.unit)
      : "and above";
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

const houseLegend = rangeLegendFromStops(publicContextMetric("house_price").stops, {
  metricId: "house_price",
  unit: "£",
});
assert.match(houseLegend.ranges[0].from, /^£/);

// Rent / fiscal metrics → opaque bands, no published £ figures.
for (const id of ["agr_plot", "vacant_residual", "net_contribution"]) {
  const metric = METRICS.find((m) => m.id === id);
  const legend = rangeLegendFromStops(metric.stops, {
    metricId: metric.id,
    unit: metric.unit,
  });
  assert.equal(legend.ranges[0].from.startsWith("Band"), true, id);
  assert.doesNotMatch(JSON.stringify(legend), /£\d/, id);
}

// Hidden choropleth must bind to public density, never AGR paint default.
const paintOff = paintMetricForChoropleth("off");
assert.equal(paintOff.id, "pop_density");
assert.equal(paintOff.property, "population_density_per_km2");

console.log("test-map-colour-ramps: ok");
