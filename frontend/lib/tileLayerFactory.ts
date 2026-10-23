/**
 * ARCH-2b: build MapLibre vector sources/layers from /v1/tiles/manifest.json.
 * Pure module — no React.
 */

export const TILE_WANTED_IDS = [
  "dz2022",
  "oil-fields",
  "platforms",
  "pipelines",
] as const;

export type TileWantedId = (typeof TILE_WANTED_IDS)[number];

const LAYER_ID_RE = /^[a-z0-9-]{1,40}$/;
const VERSION_RE = /^\d{4}-\d{2}-\d{2}\.[0-9a-f]{8}$/;
const COLOR_RE = /^#[0-9a-fA-F]{6}$/;

const FILL_PAINT = new Set([
  "fill-antialias",
  "fill-opacity",
  "fill-color",
  "fill-outline-color",
  "fill-translate",
  "fill-translate-anchor",
  "fill-pattern",
]);
const LINE_PAINT = new Set([
  "line-opacity",
  "line-color",
  "line-translate",
  "line-translate-anchor",
  "line-width",
  "line-gap-width",
  "line-offset",
  "line-blur",
  "line-dasharray",
  "line-pattern",
  "line-gradient",
]);
const CIRCLE_PAINT = new Set([
  "circle-radius",
  "circle-color",
  "circle-blur",
  "circle-opacity",
  "circle-translate",
  "circle-translate-anchor",
  "circle-pitch-scale",
  "circle-pitch-alignment",
  "circle-stroke-width",
  "circle-stroke-color",
  "circle-stroke-opacity",
]);

export class TileManifestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TileManifestError";
  }
}

export type TileLegendItem = { label: string; color: string };

export type TileManifestEntry = {
  layer: string;
  version: string;
  minzoom: number;
  maxzoom: number;
  geometry: "polygon" | "line" | "point";
  style: {
    fill?: Record<string, unknown>;
    line?: Record<string, unknown>;
    circle?: Record<string, unknown>;
  };
  legend: TileLegendItem[];
  attribution: string;
  measure: string | null;
  source_layer: string;
  title?: string;
};

export type TileManifest = {
  schema: 1;
  tilesets: Record<string, TileManifestEntry>;
};

export type BuiltTileLayers = {
  sources: Record<string, Record<string, unknown>>;
  layers: Array<Record<string, unknown>>;
  missing: string[];
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function assertIntZoom(v: unknown): v is number {
  return typeof v === "number" && Number.isInteger(v) && v >= 0 && v <= 22;
}

function assertPaint(
  kind: "fill" | "line" | "circle",
  paint: unknown,
  layerId: string,
): Record<string, unknown> {
  if (!isPlainObject(paint)) {
    throw new TileManifestError(`manifest: bad style ${layerId}`);
  }
  const allowed =
    kind === "fill" ? FILL_PAINT : kind === "line" ? LINE_PAINT : CIRCLE_PAINT;
  for (const key of Object.keys(paint)) {
    if (!allowed.has(key)) {
      throw new TileManifestError(`manifest: bad style ${layerId}`);
    }
  }
  return paint;
}

function parseEntry(key: string, raw: unknown): TileManifestEntry {
  if (!isPlainObject(raw)) {
    throw new TileManifestError(`manifest: bad layer id ${key}`);
  }
  const id = typeof raw.layer === "string" ? raw.layer : key;
  if (!LAYER_ID_RE.test(id) || id !== key) {
    throw new TileManifestError(`manifest: bad layer id ${id}`);
  }
  const version = raw.version;
  if (typeof version !== "string" || !VERSION_RE.test(version)) {
    throw new TileManifestError(`manifest: bad version ${id}`);
  }
  if (!assertIntZoom(raw.minzoom) || !assertIntZoom(raw.maxzoom)) {
    throw new TileManifestError(`manifest: bad zoom ${id}`);
  }
  if (raw.minzoom > raw.maxzoom) {
    throw new TileManifestError(`manifest: bad zoom ${id}`);
  }
  const geometry = raw.geometry;
  if (geometry !== "polygon" && geometry !== "line" && geometry !== "point") {
    throw new TileManifestError(`manifest: bad geometry ${id}`);
  }
  if (!isPlainObject(raw.style)) {
    throw new TileManifestError(`manifest: bad style ${id}`);
  }
  const styleIn = raw.style;
  for (const k of Object.keys(styleIn)) {
    if (k !== "fill" && k !== "line" && k !== "circle") {
      throw new TileManifestError(`manifest: bad style ${id}`);
    }
  }
  const style: TileManifestEntry["style"] = {};
  if ("fill" in styleIn) style.fill = assertPaint("fill", styleIn.fill, id);
  if ("line" in styleIn) style.line = assertPaint("line", styleIn.line, id);
  if ("circle" in styleIn) {
    style.circle = assertPaint("circle", styleIn.circle, id);
  }
  if (!Array.isArray(raw.legend)) {
    throw new TileManifestError(`manifest: bad legend ${id}`);
  }
  const legend: TileLegendItem[] = [];
  for (const item of raw.legend) {
    if (
      !isPlainObject(item) ||
      typeof item.label !== "string" ||
      typeof item.color !== "string" ||
      !COLOR_RE.test(item.color)
    ) {
      throw new TileManifestError(`manifest: bad legend ${id}`);
    }
    legend.push({ label: item.label, color: item.color });
  }
  if (typeof raw.attribution !== "string" || raw.attribution.length === 0) {
    throw new TileManifestError(`manifest: bad attribution ${id}`);
  }
  const measure =
    raw.measure === undefined || raw.measure === null
      ? null
      : typeof raw.measure === "string"
        ? raw.measure
        : null;
  const source_layer =
    typeof raw.source_layer === "string" && raw.source_layer
      ? raw.source_layer
      : id;
  return {
    layer: id,
    version,
    minzoom: raw.minzoom,
    maxzoom: raw.maxzoom,
    geometry,
    style,
    legend,
    attribution: raw.attribution,
    measure,
    source_layer,
    title: typeof raw.title === "string" ? raw.title : undefined,
  };
}

/** Parse a JSON text body; surfaces invalid JSON as ``manifest: invalid json``. */
export function parseTileManifestText(text: string): TileManifest {
  if (text === "") {
    throw new TileManifestError("manifest: invalid json");
  }
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new TileManifestError("manifest: invalid json");
  }
  return parseTileManifest(raw);
}

export function parseTileManifest(raw: unknown): TileManifest {
  if (raw === undefined) {
    throw new TileManifestError("manifest: not an object");
  }
  if (!isPlainObject(raw)) {
    throw new TileManifestError("manifest: not an object");
  }
  if (raw.schema !== 1) {
    throw new TileManifestError("manifest: unsupported schema");
  }
  if (!isPlainObject(raw.tilesets)) {
    throw new TileManifestError("manifest: tilesets missing");
  }
  const tilesets: Record<string, TileManifestEntry> = {};
  for (const [key, entry] of Object.entries(raw.tilesets)) {
    tilesets[key] = parseEntry(key, entry);
  }
  return { schema: 1, tilesets };
}

export function buildTileLayers(
  manifest: TileManifest,
  wanted: readonly string[] = TILE_WANTED_IDS,
): BuiltTileLayers {
  const sources: Record<string, Record<string, unknown>> = {};
  const layers: Array<Record<string, unknown>> = [];
  const missing: string[] = [];

  for (const id of wanted) {
    const entry = manifest.tilesets[id];
    if (!entry) {
      missing.push(id);
      continue;
    }
    const sourceId = `tile-${id}`;
    sources[sourceId] = {
      type: "vector",
      tiles: [
        `/backend/v1/tiles/${entry.layer}/${entry.version}/{z}/{x}/{y}.mvt`,
      ],
      minzoom: entry.minzoom,
      maxzoom: entry.maxzoom,
      promoteId: "feature_id",
      attribution: entry.attribution,
    };
    const sourceLayer = entry.source_layer || entry.layer;

    if (entry.geometry === "polygon") {
      if (entry.style.fill) {
        layers.push({
          id: `tile-${id}-fill`,
          type: "fill",
          source: sourceId,
          "source-layer": sourceLayer,
          paint: { ...entry.style.fill },
        });
      }
      if (entry.style.line) {
        layers.push({
          id: `tile-${id}-line`,
          type: "line",
          source: sourceId,
          "source-layer": sourceLayer,
          paint: { ...entry.style.line },
        });
      }
    } else if (entry.geometry === "line") {
      if (entry.style.line) {
        layers.push({
          id: `tile-${id}-line`,
          type: "line",
          source: sourceId,
          "source-layer": sourceLayer,
          paint: { ...entry.style.line },
        });
      }
    } else if (entry.geometry === "point") {
      if (entry.style.circle) {
        layers.push({
          id: `tile-${id}-circle`,
          type: "circle",
          source: sourceId,
          "source-layer": sourceLayer,
          paint: { ...entry.style.circle },
        });
      }
    }
  }

  return { sources, layers, missing };
}

export type MeasureValuesPayload = {
  layer?: string;
  version?: string;
  measure?: string;
  values: Record<string, number>;
};

type FeatureStateMap = {
  setFeatureState: (
    target: { source: string; sourceLayer: string; id: string | number },
    state: Record<string, unknown>,
  ) => void;
};

export function applyMeasureValues(
  map: FeatureStateMap,
  sourceId: string,
  sourceLayer: string,
  payload: unknown,
): void {
  if (!isPlainObject(payload) || !isPlainObject(payload.values)) {
    throw new TileManifestError("values: bad payload");
  }
  const values = payload.values;
  const validated: Record<string, number> = {};
  for (const [code, v] of Object.entries(values)) {
    if (typeof v !== "number" || !Number.isFinite(v)) {
      throw new TileManifestError("values: bad payload");
    }
    validated[code] = v;
  }
  for (const [code, v] of Object.entries(validated)) {
    map.setFeatureState(
      { source: sourceId, sourceLayer, id: code },
      { v },
    );
  }
}
