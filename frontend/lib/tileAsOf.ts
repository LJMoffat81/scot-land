/**
 * SRC-C C3 — parse a tile manifest version into a visitor-facing as-of date.
 * Version form matches tileLayerFactory VERSION_RE: YYYY-MM-DD.<sha8>.
 */

const VERSION_RE = /^\d{4}-\d{2}-\d{2}\.[0-9a-f]{8}$/;

const MONTHS_EN_GB = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

const DEFAULT_DRAWER_TILESET_MAPPING: Readonly<
  Record<string, readonly string[]>
> = {
  councils: ["councils"],
  data_zones: ["dz2022"],
  "9": ["oil-fields", "platforms", "pipelines"],
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Return e.g. "1 Oct 2026" (en-GB, UTC) for a valid calendar date version.
 * Returns null for any other value (wrong type, bad shape, impossible date).
 */
export function asOfFromVersion(v: unknown): string | null {
  if (typeof v !== "string") return null;
  if (!VERSION_RE.test(v)) return null;
  const datePart = v.slice(0, 10);
  const [ys, ms, ds] = datePart.split("-");
  const year = Number(ys);
  const month = Number(ms);
  const day = Number(ds);
  if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
    return null;
  }
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  // Construct in UTC and require the components round-trip (rejects Feb 30 etc.).
  const utc = new Date(Date.UTC(year, month - 1, day));
  if (
    utc.getUTCFullYear() !== year ||
    utc.getUTCMonth() !== month - 1 ||
    utc.getUTCDate() !== day
  ) {
    return null;
  }
  return `${day} ${MONTHS_EN_GB[month - 1]} ${year}`;
}

/**
 * ARCH-5a — drawer layer id → first valid as-of date from mapped tileset versions.
 */
export function asOfMapForDrawerLayers(
  tilesets: unknown,
  mapping: Readonly<Record<string, readonly string[]>> = DEFAULT_DRAWER_TILESET_MAPPING,
): Record<string, string> {
  if (tilesets === undefined || tilesets === null) {
    return {};
  }
  if (!isPlainObject(tilesets)) {
    throw new Error("REGISTRY-ASOF: tilesets must be an object");
  }
  if (!isPlainObject(mapping)) {
    throw new Error("REGISTRY-ASOF: mapping must be an object");
  }

  const out: Record<string, string> = {};
  for (const drawerId of Object.keys(mapping)) {
    const keys = mapping[drawerId];
    if (
      !Array.isArray(keys) ||
      !keys.every((k) => typeof k === "string" && k.trim() !== "")
    ) {
      throw new Error(
        `REGISTRY-ASOF: ${drawerId}: keys must be an array of strings`,
      );
    }
    for (const key of keys) {
      const entry = tilesets[key];
      if (entry === undefined || entry === null) continue;
      if (!isPlainObject(entry)) {
        throw new Error(
          `REGISTRY-ASOF: ${drawerId}: tileset '${key}' must be an object`,
        );
      }
      if (out[drawerId]) continue;
      const date = asOfFromVersion(entry.version);
      if (date) out[drawerId] = date;
    }
  }
  return out;
}
