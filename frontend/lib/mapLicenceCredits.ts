/**
 * Map licence credits driven by GET /layers/catalog licence fields.
 * Builds attribution lines, non-commercial badge state, no-data paint,
 * and range-legend labels (never public rent £ figures).
 */

import {
  LAYER_ATTRIBUTION,
  layerLicence,
  type CatalogLayer,
} from "@/lib/layerCatalog";

/** Grey fill when a choropleth property is missing (honest gap, not zero). */
export const NO_DATA_FILL = "#bdbdbd";

/** MapLibre image id for the diagonal hatch used on no-data polygons. */
export const NO_DATA_HATCH_IMAGE = "scot-land-no-data-hatch";

export type MapCreditEntry = {
  layerId: string;
  label: string;
  licence: string;
  licenceUrl?: string;
  attribution: string;
  nonCommercial: boolean;
};

/** True when the catalogue licence is a non-commercial (or NC research) grant. */
export function isNonCommercialLicence(licence: string | undefined | null): boolean {
  if (!licence) return false;
  const lower = licence.toLowerCase();
  return (
    lower.includes("non-commercial") ||
    lower.includes("non commercial") ||
    /\bnc\b/.test(lower)
  );
}

/**
 * Prefer catalog `attribution`, then `licence_note`, then a short licence line.
 * Never invents rent £ figures.
 */
export function creditTextFromCatalog(layer: CatalogLayer): string {
  const attribution = layer.attribution?.trim();
  if (attribution) return attribution;
  const note = layer.licence_note?.trim();
  if (note) return note;
  const licence = layerLicence(layer);
  const label = layer.label || layer.id;
  return `${label} — ${licence}`;
}

/** Build one credit row from a catalog layer (null when nothing useful to show). */
export function creditEntryFromCatalog(layer: CatalogLayer): MapCreditEntry | null {
  const licence = layerLicence(layer);
  const attribution = creditTextFromCatalog(layer);
  if (!licence && !attribution) return null;
  return {
    layerId: layer.id,
    label: layer.label || layer.id,
    licence,
    licenceUrl: layer.licence_url?.trim() || undefined,
    attribution,
    nonCommercial: isNonCommercialLicence(licence) || isNonCommercialLicence(attribution),
  };
}

/** Credits for layers that are currently painted / credited on the map. */
export function activeMapCredits(
  catalogLayers: CatalogLayer[],
  activeLayerIds: Iterable<string>,
): MapCreditEntry[] {
  const wanted = new Set(
    [...activeLayerIds].map((id) => id.trim()).filter(Boolean),
  );
  if (wanted.size === 0) return [];
  const byId = new Map(catalogLayers.map((layer) => [layer.id, layer]));
  const out: MapCreditEntry[] = [];
  for (const id of wanted) {
    const layer = byId.get(id);
    if (layer) {
      const entry = creditEntryFromCatalog(layer);
      if (entry) out.push(entry);
      continue;
    }
    // Catalog fetch can fail in smoke (no API) — fall back to known licence lines.
    const fallback = LAYER_ATTRIBUTION[id];
    if (!fallback) continue;
    const attribution = `${fallback.source} — ${fallback.licence}`;
    out.push({
      layerId: id,
      label: fallback.source,
      licence: fallback.licence,
      licenceUrl: fallback.sourceUrl,
      attribution,
      nonCommercial: isNonCommercialLicence(fallback.licence),
    });
  }
  return out;
}

export function anyNonCommercial(credits: MapCreditEntry[]): boolean {
  return credits.some((c) => c.nonCommercial);
}

/** Compact attribution string for MapLibre AttributionControl. */
export function attributionControlText(credits: MapCreditEntry[]): string {
  const seen = new Set<string>();
  const parts: string[] = [];
  for (const credit of credits) {
    const text = credit.attribution.trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    parts.push(text);
  }
  return parts.join(" · ");
}

export type RangeLegendStop = {
  /** Inclusive lower bound label (no £ for rent metrics). */
  from: string;
  /** Exclusive upper bound label, or "and above" for the last stop. */
  to: string;
  color: string;
  /**
   * Optional plain label (SW-045 Land / categorical layers).
   * When set, the legend shows this instead of from–to.
   */
  label?: string;
};

/**
 * Turn interpolate stops into range labels.
 * Rent / AGR / charge metrics are labelled as bands without publishing £ figures,
 * unless GBP-LIVE is on and the caller sets ``allowRentGbp`` (surface rent only).
 */
export function rangeLegendFromStops(
  stops: Array<[number, string]>,
  opts?: { metricId?: string; unit?: string; allowRentGbp?: boolean },
): { ranges: RangeLegendStop[]; noData: { label: string; color: string } } {
  const metricId = opts?.metricId ?? "";
  const withholdPounds = isRentMetricId(metricId) && !opts?.allowRentGbp;
  const ranges: RangeLegendStop[] = [];
  for (let i = 0; i < stops.length; i += 1) {
    const [value, color] = stops[i];
    const next = stops[i + 1];
    const from = withholdPounds
      ? bandLabel(i, stops.length)
      : formatStopValue(value, opts?.unit);
    const to = next
      ? withholdPounds
        ? bandLabel(i + 1, stops.length)
        : formatStopValue(next[0], opts?.unit)
      : "and above";
    ranges.push({ from, to, color });
  }
  return {
    ranges,
    noData: { label: "No data", color: NO_DATA_FILL },
  };
}

export function isRentMetricId(metricId: string): boolean {
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

function bandLabel(index: number, total: number): string {
  if (total <= 1) return "Band";
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  if (index < letters.length) return `Band ${letters[index]}`;
  return `Band ${index + 1}`;
}

/**
 * Format a legend stop. Unit belongs in the legend title except for £ context
 * house prices (market context, not AGR rent). Never publish rent £ figures —
 * callers must pass rent metrics through `isRentMetricId` band labels instead.
 */
function formatStopValue(value: number, unit?: string): string {
  const n = Number.isFinite(value) ? value : 0;
  const formatted =
    Math.abs(n) >= 1000
      ? n.toLocaleString("en-GB", { maximumFractionDigits: 0 })
      : String(n);
  // Context house-price metrics may use £ — that is market context, not AGR rent.
  if (unit === "£" || unit?.startsWith("£")) return `£${formatted}`;
  return formatted;
}

/**
 * MapLibre fill-color expression: grey when the property is missing / non-numeric,
 * otherwise the interpolate ramp. Does not treat missing as zero.
 */
export function paintForMetricWithNoData(
  property: string,
  stops: Array<[number, string]>,
): unknown[] {
  const flat = stops.flatMap(([v, c]) => [v, c]);
  return [
    "case",
    ["==", ["typeof", ["get", property]], "number"],
    ["interpolate", ["linear"], ["get", property], ...flat],
    NO_DATA_FILL,
  ];
}

/**
 * Build an 8×8 diagonal hatch ImageData for MapLibre `addImage`.
 * Grey ground with darker strokes — reads as "no data" beside solid ramps.
 */
export function createNoDataHatchImageData(
  size = 8,
): { width: number; height: number; data: Uint8Array } {
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const i = (y * size + x) * 4;
      const onDiag = (x + y) % size === 0 || (x + y) % size === 1;
      if (onDiag) {
        data[i] = 120;
        data[i + 1] = 120;
        data[i + 2] = 120;
        data[i + 3] = 220;
      } else {
        data[i] = 189;
        data[i + 1] = 189;
        data[i + 2] = 189;
        data[i + 3] = 255;
      }
    }
  }
  return { width: size, height: size, data };
}
