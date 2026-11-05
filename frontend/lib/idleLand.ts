/**
 * M2 Idle land — council-level vacant and derelict land payload.
 * Official SG SVDLS 2025 Table 2 figures only. Fails closed. No owner names, no postcodes,
 * no pound sign, no data below council level.
 */

import { LAND_WORTH_CIVIDIS } from "./landWorthCividis.mjs";

export const IDLE_LAND_LAYER_ID = "idle_land";
export const IDLE_LAND_FILL_ID = "idle-land-fill";
export const IDLE_LAND_ROUTE = "/platform/idle-land";
export const IDLE_LAND_VINTAGE = "2025";
export const IDLE_LAND_LEVEL = "council";
export const IDLE_LAND_FILL_OPACITY = 0.72;

export const IDLE_LAND_TABLE_HEADING = "Vacant and derelict land by council";
export const IDLE_LAND_COL_COUNCIL = "Council";
export const IDLE_LAND_COL_SITES = "Sites";
export const IDLE_LAND_COL_HECTARES = "Hectares";

export const IDLE_LAND_HA_LESS_THAN_ONE = "Less than 1";

/** Four evenly spaced cividis steps, lightest first to darkest. */
export function idleLandCividisColors(): string[] {
  const ramp = LAND_WORTH_CIVIDIS;
  const last = ramp.length - 1;
  const count = 4;
  return Array.from({ length: count }, (_, i) => {
    const idx = last - Math.round((i * last) / (count - 1));
    return ramp[idx]!;
  });
}

const BAND_COLORS = idleLandCividisColors();

export const IDLE_LAND_BANDS = [
  { id: "ha_under_10", label: "Under 10 hectares", color: BAND_COLORS[0] },
  { id: "ha_10_to_100", label: "10 to 100 hectares", color: BAND_COLORS[1] },
  { id: "ha_100_to_1000", label: "100 to 1,000 hectares", color: BAND_COLORS[2] },
  { id: "ha_1000_plus", label: "1,000 hectares or more", color: BAND_COLORS[3] },
] as const;

export function formatIdleLandHectares(areaHa: number): string {
  if (areaHa > 0 && Math.round(areaHa) < 1) return IDLE_LAND_HA_LESS_THAN_ONE;
  return Math.round(areaHa).toLocaleString("en-GB");
}

export type IdleLandBandId = (typeof IDLE_LAND_BANDS)[number]["id"];

export const IDLE_LAND_COUNCIL_CODES = [
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

const COUNCIL_SET = new Set<string>(IDLE_LAND_COUNCIL_CODES);
const BAND_IDS = new Set<string>(IDLE_LAND_BANDS.map((b) => b.id));
const BAND_COLOR: Record<string, string> = Object.fromEntries(
  IDLE_LAND_BANDS.map((b) => [b.id, b.color]),
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

const ROW_KEYS = ["area_ha", "band", "code", "name", "return_year", "site_count"] as const;

const NAME_FIELDS = [
  "asset_name",
  "group_name",
  "site_name",
  "owner_1",
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

export class IdleLandRefused extends Error {
  constructor(reason: string) {
    super(`IDLE-LAND: REFUSED: ${reason}`);
    this.name = "IdleLandRefused";
  }
}

export type IdleLandCouncil = {
  code: string;
  name: string;
  site_count: number;
  area_ha: number;
  band: IdleLandBandId;
  return_year: number;
};

export type IdleLandPayload = {
  layer_id: "idle_land";
  level: "council";
  vintage: "2025";
  source: {
    attribution: string;
    credit: string;
    licence: string;
    publication_url: string;
    dataset_url: string;
  };
  totals: { site_count: number; area_ha: number };
  bands: ReadonlyArray<{ id: IdleLandBandId; label: string; color: string }>;
  councils: IdleLandCouncil[];
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
  throw new IdleLandRefused(reason);
}

export function parseIdleLandPayload(raw: unknown): IdleLandPayload {
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
  if (raw.layer_id !== IDLE_LAND_LAYER_ID) {
    refuse("layer_id: expected idle_land");
  }
  if (raw.level !== IDLE_LAND_LEVEL) refuse("level: expected council");
  if (raw.vintage !== IDLE_LAND_VINTAGE) refuse("vintage: expected 2025");
  if (!isPlainObject(raw.source)) refuse("source keys do not match contract");
  if (keySet(raw.source) !== expectedKeys(SOURCE_KEYS)) {
    refuse("source keys do not match contract");
  }
  if (typeof raw.source.licence !== "string" || !raw.source.licence.trim()) {
    refuse("source keys do not match contract");
  }
  if (!isPlainObject(raw.totals)) refuse("payload keys do not match contract");
  if (
    typeof raw.totals.site_count !== "number" ||
    typeof raw.totals.area_ha !== "number"
  ) {
    refuse("payload keys do not match contract");
  }
  if (!Array.isArray(raw.bands)) refuse("payload keys do not match contract");
  if (raw.bands.length !== IDLE_LAND_BANDS.length) {
    refuse("bands: expected locked ids and labels");
  }
  for (let i = 0; i < IDLE_LAND_BANDS.length; i += 1) {
    const want = IDLE_LAND_BANDS[i];
    const got = raw.bands[i];
    if (!isPlainObject(got) || got.id !== want.id || got.label !== want.label) {
      refuse("bands: expected locked ids and labels");
    }
  }
  if (!Array.isArray(raw.councils)) refuse("councils: expected list");
  if (raw.councils.length !== 32) refuse("councils: expected 32 councils");
  const seen = new Set<string>();
  const councils: IdleLandCouncil[] = [];
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
    if (typeof row.site_count !== "number" || !Number.isFinite(row.site_count)) {
      refuse("council row keys do not match contract");
    }
    if (typeof row.area_ha !== "number" || !Number.isFinite(row.area_ha)) {
      refuse("council row keys do not match contract");
    }
    if (typeof row.band !== "string" || !BAND_IDS.has(row.band)) {
      refuse(`council ${code}: unknown band`);
    }
    if (typeof row.return_year !== "number" || !Number.isFinite(row.return_year)) {
      refuse("council row keys do not match contract");
    }
    councils.push({
      code,
      name: row.name.trim(),
      site_count: row.site_count,
      area_ha: row.area_ha,
      band: row.band as IdleLandBandId,
      return_year: row.return_year,
    });
  }
  if (seen.size !== 32) refuse("councils: expected 32 councils");
  return {
    layer_id: "idle_land",
    level: "council",
    vintage: "2025",
    source: {
      attribution: String(raw.source.attribution),
      credit: String(raw.source.credit),
      licence: String(raw.source.licence),
      publication_url: String(raw.source.publication_url),
      dataset_url: String(raw.source.dataset_url),
    },
    totals: {
      site_count: raw.totals.site_count,
      area_ha: raw.totals.area_ha,
    },
    bands: IDLE_LAND_BANDS.map((b) => ({ ...b })),
    councils,
  };
}

/** MapLibre match expression on council feature property `code`. */
export function idleLandFillColor(payload: IdleLandPayload): unknown[] {
  const expr: unknown[] = ["match", ["get", "code"]];
  for (const row of payload.councils) {
    expr.push(row.code, BAND_COLOR[row.band]);
  }
  expr.push("#d9d9d9");
  return expr;
}

export async function fetchIdleLand(
  baseUrl: string,
  signal?: AbortSignal,
): Promise<IdleLandPayload | null> {
  try {
    const res = await fetch(`${baseUrl}${IDLE_LAND_ROUTE}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal,
    });
    if (res.status !== 200) return null;
    return parseIdleLandPayload(await res.json());
  } catch (err: unknown) {
    if (err instanceof IdleLandRefused) {
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
export function syntheticIdleLandPayload(
  patch?: Record<string, unknown>,
): Record<string, unknown> {
  const councils = IDLE_LAND_COUNCIL_CODES.map((code, i) => ({
    code,
    name: `Synthetic council ${code.slice(-2)}`,
    site_count: 1,
    area_ha: i + 1,
    band: IDLE_LAND_BANDS[i % IDLE_LAND_BANDS.length].id,
    return_year: 2025,
  }));
  return {
    layer_id: IDLE_LAND_LAYER_ID,
    level: IDLE_LAND_LEVEL,
    vintage: IDLE_LAND_VINTAGE,
    source: {
      attribution: "Synthetic attribution",
      credit: "Synthetic credit",
      licence: "Open Government Licence v3.0",
      publication_url: "https://www.gov.scot/publications/scottish-vacant-and-derelict-land-survey-2025/",
      dataset_url: "https://www.gov.scot/publications/scottish-vacant-and-derelict-land-survey-2025/documents/",
    },
    totals: { site_count: 32, area_ha: 528 },
    bands: IDLE_LAND_BANDS.map((b) => ({ id: b.id, label: b.label, color: b.color })),
    councils,
    ...patch,
  };
}
