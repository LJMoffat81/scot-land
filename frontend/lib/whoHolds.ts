/**
 * M5 Who holds Scotland — council-level community ownership payload.
 * Official SG 2024 figures only. Fails closed. No owner names, no postcodes,
 * no pound sign, no data below council level.
 */

import { LAND_WORTH_CIVIDIS } from "./landWorthCividis.mjs";

export const WHO_HOLDS_LAYER_ID = "who_holds";
export const WHO_HOLDS_FILL_ID = "who-holds-fill";
export const WHO_HOLDS_ROUTE = "/platform/who-holds";
export const WHO_HOLDS_VINTAGE = "2024";
export const WHO_HOLDS_LEVEL = "council";
export const WHO_HOLDS_FILL_OPACITY = 0.72;

export const WHO_HOLDS_TABLE_HEADING = "Community-owned land by council";
export const WHO_HOLDS_COL_COUNCIL = "Council";
export const WHO_HOLDS_COL_ASSETS = "Assets";
export const WHO_HOLDS_COL_HECTARES = "Hectares";

export const WHO_HOLDS_HA_LESS_THAN_ONE = "Less than 1";

/** Four evenly spaced cividis steps, lightest first (S38) to darkest (S41). */
export function whoHoldsCividisColors(): string[] {
  const ramp = LAND_WORTH_CIVIDIS;
  const last = ramp.length - 1;
  const count = 4;
  return Array.from({ length: count }, (_, i) => {
    const idx = last - Math.round((i * last) / (count - 1));
    return ramp[idx]!;
  });
}

const BAND_COLORS = whoHoldsCividisColors();

export const WHO_HOLDS_BANDS = [
  { id: "ha_under_10", label: "Under 10 hectares", color: BAND_COLORS[0] },
  { id: "ha_10_to_100", label: "10 to 100 hectares", color: BAND_COLORS[1] },
  { id: "ha_100_to_1000", label: "100 to 1,000 hectares", color: BAND_COLORS[2] },
  { id: "ha_1000_plus", label: "1,000 hectares or more", color: BAND_COLORS[3] },
] as const;

export function formatWhoHoldsHectares(areaHa: number): string {
  if (areaHa > 0 && Math.round(areaHa) < 1) return WHO_HOLDS_HA_LESS_THAN_ONE;
  return Math.round(areaHa).toLocaleString("en-GB");
}

export type WhoHoldsBandId = (typeof WHO_HOLDS_BANDS)[number]["id"];

export const WHO_HOLDS_COUNCIL_CODES = [
  "S12000005",
  "S12000006",
  "S12000008",
  "S12000010",
  "S12000011",
  "S12000013",
  "S12000014",
  "S12000017",
  "S12000018",
  "S12000019",
  "S12000020",
  "S12000021",
  "S12000023",
  "S12000026",
  "S12000027",
  "S12000028",
  "S12000029",
  "S12000030",
  "S12000033",
  "S12000034",
  "S12000035",
  "S12000036",
  "S12000038",
  "S12000039",
  "S12000040",
  "S12000041",
  "S12000042",
  "S12000045",
  "S12000047",
  "S12000048",
  "S12000049",
  "S12000050",
] as const;

const COUNCIL_SET = new Set<string>(WHO_HOLDS_COUNCIL_CODES);
const BAND_IDS = new Set<string>(WHO_HOLDS_BANDS.map((b) => b.id));
const BAND_COLOR: Record<string, string> = Object.fromEntries(
  WHO_HOLDS_BANDS.map((b) => [b.id, b.color]),
);

const PAYLOAD_KEYS = [
  "bands",
  "councils",
  "layer_id",
  "level",
  "source",
  "totals",
  "vintage",
] as const;

const SOURCE_KEYS = [
  "attribution",
  "credit",
  "dataset_url",
  "licence",
  "publication_url",
] as const;

const ROW_KEYS = ["area_ha", "asset_count", "band", "code", "name"] as const;

const NAME_FIELDS = [
  "asset_name",
  "group_name",
  "owner",
  "owner_name",
  "individual",
  "person",
  "postcode",
  "contact",
  "address",
];

const POUND = "\u00a3";
const CODE_RE = /^S12\d{6}$/;

export class WhoHoldsRefused extends Error {
  constructor(reason: string) {
    super(`WHO-HOLDS: REFUSED: ${reason}`);
    this.name = "WhoHoldsRefused";
  }
}

export type WhoHoldsCouncil = {
  code: string;
  name: string;
  asset_count: number;
  area_ha: number;
  band: WhoHoldsBandId;
};

export type WhoHoldsPayload = {
  layer_id: "who_holds";
  level: "council";
  vintage: "2024";
  source: {
    attribution: string;
    credit: string;
    licence: string;
    publication_url: string;
    dataset_url: string;
  };
  totals: { asset_count: number; area_ha: number };
  bands: ReadonlyArray<{ id: WhoHoldsBandId; label: string; color: string }>;
  councils: WhoHoldsCouncil[];
};

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function keySet(obj: Record<string, unknown>): string {
  return Object.keys(obj).sort().join(",");
}

function expectedKeys(keys: readonly string[]): string {
  return [...keys].sort().join(",");
}

function refuse(reason: string): never {
  throw new WhoHoldsRefused(reason);
}

export function parseWhoHoldsPayload(raw: unknown): WhoHoldsPayload {
  if (!isPlainObject(raw)) refuse("payload: expected object");
  const dumped = JSON.stringify(raw);
  if (dumped.includes(POUND) || /gbp/i.test(dumped)) {
    refuse("payload contains a pound sign");
  }
  for (const field of NAME_FIELDS) {
    if (field in raw) refuse("extract must not contain owner names");
  }
  if (keySet(raw) !== expectedKeys(PAYLOAD_KEYS)) {
    refuse("payload keys do not match contract");
  }
  if (raw.layer_id !== WHO_HOLDS_LAYER_ID) {
    refuse("layer_id: expected who_holds");
  }
  if (raw.level !== WHO_HOLDS_LEVEL) refuse("level: expected council");
  if (raw.vintage !== WHO_HOLDS_VINTAGE) refuse("vintage: expected 2024");
  if (!isPlainObject(raw.source)) refuse("source keys do not match contract");
  if (keySet(raw.source) !== expectedKeys(SOURCE_KEYS)) {
    refuse("source keys do not match contract");
  }
  if (typeof raw.source.licence !== "string" || !raw.source.licence.trim()) {
    refuse("source keys do not match contract");
  }
  if (!isPlainObject(raw.totals)) refuse("payload keys do not match contract");
  if (
    typeof raw.totals.asset_count !== "number" ||
    typeof raw.totals.area_ha !== "number"
  ) {
    refuse("payload keys do not match contract");
  }
  if (!Array.isArray(raw.bands)) refuse("payload keys do not match contract");
  if (raw.bands.length !== WHO_HOLDS_BANDS.length) {
    refuse("bands: expected locked ids and labels");
  }
  for (let i = 0; i < WHO_HOLDS_BANDS.length; i += 1) {
    const want = WHO_HOLDS_BANDS[i];
    const got = raw.bands[i];
    if (!isPlainObject(got) || got.id !== want.id || got.label !== want.label) {
      refuse("bands: expected locked ids and labels");
    }
  }
  if (!Array.isArray(raw.councils)) refuse("councils: expected list");
  if (raw.councils.length !== 32) refuse("councils: expected 32 councils");
  const seen = new Set<string>();
  const councils: WhoHoldsCouncil[] = [];
  for (const row of raw.councils) {
    if (!isPlainObject(row)) refuse("council row keys do not match contract");
    for (const field of NAME_FIELDS) {
      if (field in row) refuse("extract must not contain owner names");
    }
    if (keySet(row) !== expectedKeys(ROW_KEYS)) {
      refuse("council row keys do not match contract");
    }
    const code = row.code;
    if (typeof code !== "string" || !CODE_RE.test(code) || !COUNCIL_SET.has(code)) {
      refuse("council code: expected official council");
    }
    if (seen.has(code)) refuse(`council ${code}: listed twice`);
    seen.add(code);
    if (typeof row.name !== "string" || !row.name.trim()) {
      refuse("council row keys do not match contract");
    }
    if (typeof row.asset_count !== "number" || !Number.isFinite(row.asset_count)) {
      refuse("council row keys do not match contract");
    }
    if (typeof row.area_ha !== "number" || !Number.isFinite(row.area_ha)) {
      refuse("council row keys do not match contract");
    }
    if (typeof row.band !== "string" || !BAND_IDS.has(row.band)) {
      refuse(`council ${code}: unknown band`);
    }
    councils.push({
      code,
      name: row.name.trim(),
      asset_count: row.asset_count,
      area_ha: row.area_ha,
      band: row.band as WhoHoldsBandId,
    });
  }
  if (seen.size !== 32) refuse("councils: expected 32 councils");
  return {
    layer_id: "who_holds",
    level: "council",
    vintage: "2024",
    source: {
      attribution: String(raw.source.attribution),
      credit: String(raw.source.credit),
      licence: String(raw.source.licence),
      publication_url: String(raw.source.publication_url),
      dataset_url: String(raw.source.dataset_url),
    },
    totals: {
      asset_count: raw.totals.asset_count,
      area_ha: raw.totals.area_ha,
    },
    bands: WHO_HOLDS_BANDS.map((b) => ({ ...b })),
    councils,
  };
}

/** MapLibre match expression on council feature property `code`. */
export function whoHoldsFillColor(payload: WhoHoldsPayload): unknown[] {
  const expr: unknown[] = ["match", ["get", "code"]];
  for (const row of payload.councils) {
    expr.push(row.code, BAND_COLOR[row.band]);
  }
  expr.push("#d9d9d9");
  return expr;
}

export async function fetchWhoHolds(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<WhoHoldsPayload | null> {
  try {
    const res = await fetch(`${baseUrl}${WHO_HOLDS_ROUTE}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
    if (res.status !== 200) return null;
    return parseWhoHoldsPayload(await res.json());
  } catch (err: unknown) {
    if (err instanceof WhoHoldsRefused) {
      console.warn(err.message);
      return null;
    }
    if (err instanceof SyntaxError) return null;
    if (err instanceof TypeError) return null;
    if (err instanceof DOMException && err.name === "AbortError") return null;
    throw err;
  }
}

/** Synthetic 32-council payload for unit and e2e tests. Not official figures. */
export function syntheticWhoHoldsPayload(
  patch?: Record<string, unknown>,
): Record<string, unknown> {
  const councils = WHO_HOLDS_COUNCIL_CODES.map((code, i) => ({
    code,
    name: `Synthetic council ${code.slice(-2)}`,
    asset_count: 1,
    area_ha: i + 1,
    band: WHO_HOLDS_BANDS[i % WHO_HOLDS_BANDS.length].id,
  }));
  return {
    layer_id: WHO_HOLDS_LAYER_ID,
    level: WHO_HOLDS_LEVEL,
    vintage: WHO_HOLDS_VINTAGE,
    source: {
      attribution: "Synthetic attribution",
      credit: "Synthetic credit",
      licence: "Open Government Licence v3.0",
      publication_url: "https://www.gov.scot/publications/community-ownership-in-scotland-2024/",
      dataset_url: "https://www.gov.scot/publications/community-ownership-in-scotland-2024/documents/",
    },
    totals: { asset_count: 32, area_ha: 528 },
    bands: WHO_HOLDS_BANDS.map((b) => ({ id: b.id, label: b.label, color: b.color })),
    councils,
    ...patch,
  };
}
