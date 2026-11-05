/**
 * DZ-HEATMAP PR-B — estimate-status fill on the dz2011 registry tileset.
 *
 * Status categories only: no value, no band, no pound figure. 2023 is never
 * requested or shown. Fails closed: any non-200, network error, bad JSON or
 * payload that is not exactly the PR-A contract → null (no fill, no key).
 * Pure module apart from fetchDzStatus (no React).
 */

import {
  buildTileLayers,
  type TileManifest,
  type TileManifestEntry,
} from "./tileLayerFactory";

/** Backend route (PR-A). No query string: the year is fixed server-side. */
export const DZ_STATUS_ROUTE = "/platform/dz-status";

/** Registry tileset id (PR-B0, backend/layers/registry/dz2011.yaml). */
export const DZ_STATUS_TILESET = "dz2011";

/** Visitor switch id; also the PR-A payload layer_id. */
export const DZ_STATUS_LAYER_ID = "dz_status";

/** MapLibre ids owned by this layer. */
export const DZ_STATUS_SOURCE_ID = `tile-${DZ_STATUS_TILESET}`;
export const DZ_STATUS_FILL_ID = "dz-status-fill";

/** OFF by default. Turning on is the visitor's switch only. */
export const DZ_STATUS_DEFAULT_ON = false;

/** The only year this layer shows. */
export const DZ_STATUS_ESTIMATE_YEAR = 2024;

export const DZ_STATUS_VINTAGE = "DZ2011";

/** Locked Wording & UX copy (PR-A config, dz_heatmap.yaml). */
export const DZ_STATUS_KEY_TITLE = "Estimate status";
export const DZ_STATUS_VINTAGE_NOTE = "Uses 2011 local areas (data zones)";

/** PR-A payload source.credit for DZ2011 (boundary credit, verbatim). */
export const DZ_STATUS_BOUNDARY_CREDIT =
  "Scottish Government, Data Zone Boundaries 2011, Open Government Licence v3.0";

/**
 * Key credit line. PROPOSED — needs Wording & UX sign-off (SPEC §4):
 * marks the fill as a Scot-LAND estimate (GIS) without adding hint text.
 */
export const DZ_STATUS_CREDIT = `Scot-LAND estimate, not official data. Boundaries: ${DZ_STATUS_BOUNDARY_CREDIT}`;

export type DzStatusId =
  | "estimated"
  | "unavailable"
  | "model_failure"
  | "no_cell"
  | "not_scored";

/**
 * Contract order, locked labels, fill colours. Wording & UX locked condition:
 * category 1 ("Estimate available") is cividis (LAND_WORTH_CIVIDIS[0]);
 * categories 2-5 are distinguishable neutral greys, so no "No estimate" area
 * reads as data or outshines an estimated one.
 */
export const DZ_STATUS_CATEGORIES: ReadonlyArray<{
  id: DzStatusId;
  label: string;
  color: string;
}> = [
  { id: "estimated", label: "Estimate available", color: "#00224e" },
  { id: "unavailable", label: "No estimate: data not available", color: "#bdbdbd" },
  {
    id: "model_failure",
    label: "No estimate: our method doesn't work well here",
    color: "#969696",
  },
  { id: "no_cell", label: "No estimate: too few similar sales", color: "#737373" },
  {
    id: "not_scored",
    label: "No estimate: outside the areas we estimate",
    color: "#d9d9d9",
  },
];

export const DZ_STATUS_FILL_OPACITY = 0.6;

export type DzStatusPayload = {
  layer_id: string;
  data_zone_vintage: string;
  estimate_year: number;
  key_title: string;
  categories: Array<{ id: string; label: string }>;
  source: { credit: string; licence: string; attribution: string };
  vintage_note: string;
  zones: Array<{ code: string; status: DzStatusId }>;
};

export class DzStatusRefused extends Error {
  constructor(message: string) {
    super(`DZ-STATUS: REFUSED: ${message}`);
    this.name = "DzStatusRefused";
  }
}

const PAYLOAD_KEYS = [
  "categories",
  "data_zone_vintage",
  "estimate_year",
  "key_title",
  "layer_id",
  "source",
  "vintage_note",
  "zones",
];
const SOURCE_KEYS = ["attribution", "credit", "licence"];
const ZONE_KEYS = ["code", "status"];
const CODE_RE = /^S01\d{6}$/;
const STATUS_IDS = new Set<string>(DZ_STATUS_CATEGORIES.map((c) => c.id));

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function sameKeys(obj: Record<string, unknown>, keys: readonly string[]): boolean {
  const got = Object.keys(obj).sort();
  return got.length === keys.length && got.every((k, i) => k === keys[i]);
}

/** Validate the PR-A payload exactly; throws DzStatusRefused on any deviation. */
export function parseDzStatusPayload(raw: unknown): DzStatusPayload {
  if (!isPlainObject(raw)) throw new DzStatusRefused("payload: expected object");
  const text = JSON.stringify(raw);
  if (text.includes("\u00a3") || /gbp/i.test(text)) {
    throw new DzStatusRefused("payload contains a pound sign");
  }
  if (!sameKeys(raw, PAYLOAD_KEYS)) {
    throw new DzStatusRefused("payload keys do not match contract");
  }
  if (raw.layer_id !== DZ_STATUS_LAYER_ID) {
    throw new DzStatusRefused("layer_id: expected dz_status");
  }
  if (raw.data_zone_vintage !== DZ_STATUS_VINTAGE) {
    throw new DzStatusRefused("data_zone_vintage: expected DZ2011");
  }
  if (raw.estimate_year === 2023) {
    throw new DzStatusRefused("estimate_year 2023 is never shown");
  }
  if (raw.estimate_year !== DZ_STATUS_ESTIMATE_YEAR) {
    throw new DzStatusRefused("estimate_year: expected 2024");
  }
  if (raw.key_title !== DZ_STATUS_KEY_TITLE) {
    throw new DzStatusRefused("key_title: expected locked title");
  }
  const cats = raw.categories;
  if (
    !Array.isArray(cats) ||
    cats.length !== DZ_STATUS_CATEGORIES.length ||
    !cats.every(
      (c, i) =>
        isPlainObject(c) &&
        sameKeys(c, ["id", "label"]) &&
        c.id === DZ_STATUS_CATEGORIES[i].id &&
        c.label === DZ_STATUS_CATEGORIES[i].label,
    )
  ) {
    throw new DzStatusRefused("categories: expected locked ids and labels");
  }
  const source = raw.source;
  if (!isPlainObject(source) || !sameKeys(source, SOURCE_KEYS)) {
    throw new DzStatusRefused("source keys do not match contract");
  }
  if (source.credit !== DZ_STATUS_BOUNDARY_CREDIT) {
    throw new DzStatusRefused("source.credit: expected DZ2011 boundary credit");
  }
  if (raw.vintage_note !== DZ_STATUS_VINTAGE_NOTE) {
    throw new DzStatusRefused("vintage_note: expected locked note");
  }
  const zones = raw.zones;
  if (!Array.isArray(zones) || zones.length === 0) {
    throw new DzStatusRefused("zones: expected non-empty list");
  }
  const seen = new Set<string>();
  for (const z of zones) {
    if (!isPlainObject(z) || !sameKeys(z, ZONE_KEYS)) {
      throw new DzStatusRefused("zone row keys do not match contract");
    }
    if (typeof z.code !== "string" || !CODE_RE.test(z.code)) {
      throw new DzStatusRefused("zone code: expected DZ2011 code");
    }
    if (seen.has(z.code)) {
      throw new DzStatusRefused(`zone ${z.code}: duplicate`);
    }
    seen.add(z.code);
    if (typeof z.status !== "string" || !STATUS_IDS.has(z.status)) {
      throw new DzStatusRefused(`zone ${z.code}: unknown status`);
    }
  }
  return raw as unknown as DzStatusPayload;
}

/** MapLibre fill-color: match on the tile feature_id (= DZ2011 code). */
export function dzStatusFillColor(payload: DzStatusPayload): unknown[] {
  const expr: unknown[] = ["match", ["get", "feature_id"]];
  for (const cat of DZ_STATUS_CATEGORIES) {
    const codes = payload.zones.filter((z) => z.status === cat.id).map((z) => z.code);
    if (codes.length > 0) expr.push(codes, cat.color);
  }
  expr.push("rgba(0,0,0,0)");
  return expr;
}

/** The dz2011 manifest entry, or null when the tileset is not built. */
export function dzStatusTileEntry(
  manifest: TileManifest | null | undefined,
): TileManifestEntry | null {
  const entry = manifest?.tilesets?.[DZ_STATUS_TILESET];
  return entry && entry.geometry === "polygon" ? entry : null;
}

export type DzStatusTiles = {
  source: Record<string, unknown>;
  sourceLayer: string;
};

/**
 * MapLibre vector source for the dz2011 tileset, built by the registry tile
 * factory (same URL template, promoteId and attribution as every tileset).
 * Null when the manifest has no dz2011 polygon tileset.
 */
export function dzStatusTiles(
  manifest: TileManifest,
): DzStatusTiles | null {
  const entry = dzStatusTileEntry(manifest);
  if (!entry) return null;
  const source = buildTileLayers(manifest, [DZ_STATUS_TILESET]).sources[
    DZ_STATUS_SOURCE_ID
  ];
  if (!source) return null;
  return { source, sourceLayer: entry.source_layer || entry.layer };
}

/** Fetch + validate. Non-200, network, bad JSON or refusal → null (fail closed). */
export async function fetchDzStatus(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<DzStatusPayload | null> {
  try {
    const res = await fetch(`${baseUrl}${DZ_STATUS_ROUTE}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
    if (res.status !== 200) return null;
    return parseDzStatusPayload(await res.json());
  } catch (err: unknown) {
    if (err instanceof DzStatusRefused) {
      console.warn(err.message);
      return null;
    }
    // Bad JSON body.
    if (err instanceof SyntaxError) return null;
    // Network failure (fetch rejects with TypeError).
    if (err instanceof TypeError) return null;
    if (err instanceof DOMException && err.name === "AbortError") return null;
    throw err;
  }
}
