/**
 * Node asserts for map licence credit helpers (no Playwright / browser).
 * Mirrors frontend/lib/mapLicenceCredits.ts — keep in sync when changing logic.
 */
import assert from "node:assert/strict";

function isNonCommercialLicence(licence) {
  if (!licence) return false;
  const lower = licence.toLowerCase();
  return (
    lower.includes("non-commercial") ||
    lower.includes("non commercial") ||
    /\bnc\b/.test(lower)
  );
}

function creditTextFromCatalog(layer) {
  const attribution = layer.attribution?.trim();
  if (attribution) return attribution;
  const note = layer.licence_note?.trim();
  if (note) return note;
  const licence = layer.licence?.trim() || "Licence not listed in catalog";
  return `${layer.label || layer.id} — ${licence}`;
}

function creditEntryFromCatalog(layer) {
  const licence = layer.licence?.trim() || "Licence not listed in catalog";
  const attribution = creditTextFromCatalog(layer);
  return {
    layerId: layer.id,
    label: layer.label || layer.id,
    licence,
    licenceUrl: layer.licence_url?.trim() || undefined,
    attribution,
    nonCommercial:
      isNonCommercialLicence(licence) || isNonCommercialLicence(attribution),
  };
}

const LAYER_ATTRIBUTION = {
  boundaries: {
    source: "Registers of Scotland INSPIRE Index Polygons",
    licence: "OGL-3.0",
    sourceUrl: "https://www.ros.gov.uk/open-data",
  },
};

function activeMapCredits(catalogLayers, activeLayerIds) {
  const wanted = new Set([...activeLayerIds].map((id) => id.trim()).filter(Boolean));
  const byId = new Map(catalogLayers.map((layer) => [layer.id, layer]));
  const out = [];
  for (const id of wanted) {
    const layer = byId.get(id);
    if (layer) {
      out.push(creditEntryFromCatalog(layer));
      continue;
    }
    const fallback = LAYER_ATTRIBUTION[id];
    if (!fallback) continue;
    out.push({
      layerId: id,
      label: fallback.source,
      licence: fallback.licence,
      licenceUrl: fallback.sourceUrl,
      attribution: `${fallback.source} — ${fallback.licence}`,
      nonCommercial: isNonCommercialLicence(fallback.licence),
    });
  }
  return out;
}

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

function paintForMetricWithNoData(property, stops) {
  const flat = stops.flatMap(([v, c]) => [v, c]);
  return [
    "case",
    ["==", ["typeof", ["get", property]], "number"],
    ["interpolate", ["linear"], ["get", property], ...flat],
    "#bdbdbd",
  ];
}

const boundaries = {
  id: "boundaries",
  label: "ROS INSPIRE parcels",
  licence: "OGL-3.0",
  licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
  attribution:
    "© Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right 2026. OGL-3.0.",
};

const nsta = {
  id: "nsta_oil_gas",
  label: "NSTA oil and gas",
  licence: "non-commercial",
  attribution:
    "Contains information provided by the North Sea Transition Authority and/or other third parties. Non-commercial use only.",
};

const credits = activeMapCredits([boundaries, nsta], ["boundaries", "nsta_oil_gas"]);
assert.equal(credits.length, 2);
assert.match(credits[0].attribution, /Registers of Scotland/);
assert.equal(credits[0].licenceUrl?.includes("open-government-licence"), true);
assert.equal(credits[1].nonCommercial, true);
assert.equal(isNonCommercialLicence("OGL-3.0"), false);
assert.equal(isNonCommercialLicence("non-commercial"), true);

const fallbackCredits = activeMapCredits([], ["boundaries"]);
assert.equal(fallbackCredits.length, 1);
assert.equal(fallbackCredits[0].licence, "OGL-3.0");
assert.match(fallbackCredits[0].attribution, /Registers of Scotland/);

const rentLegend = rangeLegendFromStops(
  [
    [0, "#ffffcc"],
    [500, "#c7e9b4"],
  ],
  { metricId: "agr_plot" },
);
assert.equal(rentLegend.ranges[0].from.startsWith("Band"), true);
assert.equal(rentLegend.noData.label, "No data");

const vacantLegend = rangeLegendFromStops(
  [
    [0, "#fff5eb"],
    [2_000_000, "#fdd0a2"],
  ],
  { metricId: "vacant_residual", unit: "£" },
);
assert.equal(vacantLegend.ranges[0].from.startsWith("Band"), true);
assert.doesNotMatch(JSON.stringify(vacantLegend), /£\d/);

const densityLegend = rangeLegendFromStops(
  [
    [10, "#f7fcf0"],
    [100, "#ccebc5"],
  ],
  { metricId: "pop_density", unit: "people/km²" },
);
assert.equal(densityLegend.ranges[0].from, "10");
assert.doesNotMatch(JSON.stringify(densityLegend), /£\d/);

const paint = paintForMetricWithNoData("population_density_per_km2", [
  [10, "#f7fcf0"],
  [100, "#ccebc5"],
]);
assert.equal(paint[0], "case");
assert.deepEqual(paint[1], ["==", ["typeof", ["get", "population_density_per_km2"]], "number"]);
assert.equal(paint[3], "#bdbdbd");

console.log("test-map-licence-credits: ok");
