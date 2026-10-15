/**
 * Public place-card contract (place_card_v1).
 * UX-10 place card skeleton — Annual Ground Rent; DZ2022; no £ figures.
 */

import { apiJson, isOutsideScotlandError } from "./api";
import { preferDz2022, type PlaceDataZoneVintage } from "./placeCardDz";
import {
  PLACE_CARD_PART_GLOSS,
  PLACE_CARD_PART_NOT_YET,
  defaultAgrGroupRows,
} from "./rentGroupAgrRows.mjs";
import { RENT_GROUP_NAME, RENT_GROUP_NAMES } from "./rentGroupNames.mjs";

export { dataZoneFieldLabel, preferDz2022 } from "./placeCardDz";
export { RENT_GROUP_NAME, RENT_GROUP_NAMES };
export { PLACE_CARD_PART_GLOSS, PLACE_CARD_PART_NOT_YET };

/** One public term for the figure (UX-10 terminology test). */
export const PLACE_CARD_AGR_LABEL = "Annual Ground Rent";

export const PLACE_CARD_AGR_SUBTITLE =
  "What the land here is worth each year";

/** Pre-£ figure line (UX-10 item 4). Rank band stays OFF. */
export const PLACE_CARD_PRE_POUND =
  "We're not showing amounts yet while we check our method.";

/** Rank band UI — OFF until £ unblocked (UX-10). */
export const PLACE_CARD_RANK_BAND_ENABLED = false;

export const PLACE_CARD_TYPICAL_HOME =
  "For a typical home in this neighbourhood, not your home.";

export const PLACE_CARD_NEIGHBOURHOOD_NOT_ADDRESS =
  "We show your neighbourhood, not your address.";

export const PLACE_CARD_COVERS_HOMES_ONLY = "Covers land under homes only.";

export const PLACE_CARD_HOW_WE_WORK_HOMES =
  "This covers land under homes only. Shops, offices and industrial land aren't included yet.";

export const PLACE_CARD_FACT_LINE =
  "Land is worth more where there are jobs, good transport, schools and shops nearby. Most of that comes from the area, not the house.";

export const PLACE_CARD_PARTS_NOTE =
  "These are worked out differently, so we don't add them up.";

export const PLACE_CARD_HOW_WE_WORK_LABEL = "How we work this out";

export const PLACE_CARD_EXPERIMENTAL_FOOTER =
  "Experimental estimate, not an official valuation. It is not a bill, and it does not change what you pay.";

export const PLACE_CARD_NO_HOMES = "No homes here, so not applicable";

export const PLACE_CARD_TOO_FEW_HOMES =
  "Too few homes here for a typical figure.";

export const PLACE_CARD_NO_MATCH =
  "No place matched. Try a postcode, place name, coordinates, or click the map.";

export const PLACE_CARD_FULLY_ESTIMATED =
  "Mostly worked out from nearby areas: treat as a rough guide";

/** Unit rule (v1): zones with fewer than this many dwellings are N/A, never 0. */
export const PLACE_CARD_MIN_DWELLINGS_TYPICAL = 20;

/** Per-row status until publication — keep exact wording (site rewrite PR2). */
export const PLACE_CARD_FIGURE_STATUS = "Figure not published yet";

/** @deprecated Prefer PLACE_CARD_FIGURE_STATUS on each value row. */
export const PLACE_CARD_FIGURES_CHECKED = PLACE_CARD_FIGURE_STATUS;

export const PLACE_CARD_RESEARCH_DISCLAIMER =
  "research estimate, not an official valuation or bill";

export const PLACE_CARD_CONSTRAINT_LABEL =
  "Constraint: changes best use, adds no value";

/** Fourth public group name — same as Layers /data (SW-021). */
export const PLACE_CARD_LIMITS_HEADING = "Limits";

/** @deprecated UX-10 uses PLACE_CARD_HOW_WE_WORK_LABEL. */
export const PLACE_CARD_HOW_WE_VALUE_LABEL = "How we value land";

export const PLACE_CARD_HOLDER_COPY =
  "Public records only. Private owners are not shown.";

export const PLACE_CARD_SCOTLIS_LABEL =
  "Check the official title record on ScotLIS";

/**
 * Sea / outside Scotland map click — one plain line (site-watch D3 / SW-019).
 */
export const PLACE_CARD_OUT_OF_SCOTLAND_LINE =
  "This spot is outside Scotland's land map. Tap on land to see a place.";

/** SW-028: link under the sea line — close card and reset to national map view. */
export const PLACE_CARD_SHOW_SCOTLAND_LABEL = "Show me Scotland";

/** Never show "No data" when a code is known (AGENTS.md). */
export const PLACE_CARD_NAME_NOT_LOADED = "name not loaded yet";

/** FP1 class → visitor chip (never "market price"). */
export const PLACE_CARD_CLASS_CHIP = Object.freeze({
  market: "Market",
  proxy: "Modelled",
  shadow: "Estimate",
} as const);

export type PlaceRentTag = "market" | "proxy" | "shadow";

export type PlaceCardClass = keyof typeof PLACE_CARD_CLASS_CHIP;

export type PlaceCardConfidence = "High" | "Medium" | "Low";

export type PlaceUnitKind =
  | "typical_home"
  | "too_few_homes"
  | "no_homes"
  | "not_applicable";

/** FP1 — one schema for every layer part on the card. */
export type PlacePartSchema = {
  range: string | null;
  unit: string | null;
  confidence: PlaceCardConfidence | null;
  method: string | null;
  class: PlaceCardClass | PlaceRentTag;
};

/** True when the place has no Scottish data zone (e.g. at sea). */
export function isPlaceCardSeaMiss(
  zone: { status?: string | null } | null | undefined,
): boolean {
  return zone?.status === "miss";
}

/** Place-card field label for the 3×3 m grid index. */
export const PLACE_CARD_MAP_REFERENCE_LABEL = "Map reference";

/** Shown when the map-reference Copy button cannot write the clipboard. */
export const PLACE_CARD_MAP_REFERENCE_COPY_FAIL =
  "Couldn't copy — select and copy the reference instead.";

export type PlaceValueStatus = "coming_soon" | "in_progress";

export type PlaceLayerStatus = "live" | "linked" | "gap" | string;

export type PlaceLayer = {
  id: string;
  label: string;
  status: PlaceLayerStatus;
  intersects: boolean | null;
  note?: string | null;
  source_url?: string | null;
  /** Required — every layer gets a licence credit. */
  licence?: string | null;
  licence_url?: string | null;
  detail?: Record<string, unknown> | null;
};

export type PlaceLink = {
  id: string;
  label: string;
  url: string;
};

export type PlaceDataZone = PlaceDataZoneVintage;

export type PlaceIntermediateZone = {
  status: "ok" | "no_data" | string;
  code?: string | null;
  name?: string | null;
  note?: string | null;
};

export type PlaceAgrRow = {
  id: "surface" | "resource" | "nature" | string;
  label: string;
  tag: PlaceRentTag;
  /** Public status — never a £ amount when GBP-LIVE is off. */
  status: PlaceValueStatus;
  /** When false, row is omitted from the place card. */
  applies?: boolean;
  /** Plain gloss under the part heading (UX-10 item 7). */
  gloss?: string | null;
  /** FP1 schema fields (pre-£ uses "not yet estimated" / nulls). */
  range?: string | null;
  unit?: string | null;
  confidence?: PlaceCardConfidence | null;
  method?: string | null;
  class?: PlaceCardClass | PlaceRentTag | null;
  of_which?: Array<{ id: string; label: string }>;
  /** GBP-LIVE visitor estimate label (Measured / Partly estimated / Fully estimated). */
  estimate_label?: string | null;
  /** GBP-LIVE yield wording ("up to …"). */
  yield_wording?: string | null;
  amount_label?: string | null;
};

export type PlaceConstraintRow = {
  id: string;
  label: string;
  applies: boolean | null;
  note?: string | null;
};

export type PlaceHolder = {
  status: "public_record" | "private_not_shown" | "unknown";
  label: string;
  note?: string | null;
};

export type PlaceCardPayload = {
  contract: "place_card_v1" | string;
  lat: number;
  lng: number;
  place_label?: string | null;
  postcode?: string | null;
  council_code?: string | null;
  council_name?: string | null;
  data_zone?: PlaceDataZone | null;
  intermediate_zone?: PlaceIntermediateZone | null;
  /** Map reference grid indices (`latIndex,lngIndex`) — never a what3words brand string. */
  square_reference?: string | null;
  agr_rows?: PlaceAgrRow[];
  constraints?: PlaceConstraintRow[];
  holder?: PlaceHolder | null;
  layers: PlaceLayer[];
  links: PlaceLink[];
  vacant_or_derelict?: boolean;
  flags?: string[];
  parcel?: {
    found?: boolean;
    label?: string | null;
    inspire_id?: string | null;
    area_sqm?: number | null;
    note?: string | null;
  } | null;
  /** Public land-outline block — never carries parcel ID. */
  land_outline?: {
    status?: string | null;
    label?: string | null;
    area_sqm?: number | null;
    note?: string | null;
  } | null;
  public_or_crown?: {
    on_this_point?: boolean | null;
    holdings?: Array<{
      organisation?: string | null;
      site_name?: string | null;
    }>;
    note?: string | null;
    map_url?: string | null;
  } | null;
  common_good?: {
    status?: string;
    register?: { url?: string | null; label?: string | null } | null;
    national_gap?: string | null;
    reason?: string | null;
  } | null;
  community_ownership?: {
    status?: string;
    on_this_point?: boolean | null;
    assets?: Array<{ name?: string | null }>;
    note?: string | null;
  } | null;
  private_or_sasine?: { status?: string; note?: string | null } | null;
  land_register_outline?: { status?: string; note?: string | null } | null;
  scotlis?: {
    public_home?: string;
    label?: string;
    note?: string;
    search_hint?: string;
  } | null;
  /** Must never appear on public place cards; guarded in the UI. */
  agr?: unknown;
  /** Dwelling count for the unit rule (v1). */
  dwellings?: number | null;
  /** Local sales year window for item 5. */
  sales_year_from?: number | null;
  sales_year_to?: number | null;
  /** How sure we are (item 5) — High / Medium / Low. */
  confidence?: PlaceCardConfidence | null;
  /** When true, show the fully-estimated guide line (item 5). */
  fully_estimated?: boolean;
  /** UX-10 card state override for no-match. */
  card_state?: "ok" | "no_match" | "sea" | "no_homes" | string | null;
  /** GBP-LIVE-V1 flag mirror (default OFF). */
  gbp_live?: { enabled?: boolean; banner?: string | null; yield_wording?: string | null } | null;
  /** GBP-LIVE surface rent display for this Data Zone (absent when flag OFF). */
  surface_rent_display?: {
    state?: string | null;
    label?: string | null;
    estimate_label?: string | null;
    estimate_label_key?: string | null;
    low?: number | null;
    central?: number | null;
    high?: number | null;
    yield_wording?: string | null;
    grain?: string | null;
  } | null;
};

export type FetchPlaceCardArgs = {
  lat: number;
  lng: number;
  postcode?: string | null;
};

const METERS_PER_DEGREE_LAT = 111_320.0;
const SQUARE_SIZE_M = 3.0;

/** Map reference indices from snapped 3×3 m grid (numbers only; no what3words). */
export function scotLandSquareReference(lat: number, lng: number): string {
  const latRad = (lat * Math.PI) / 180;
  const metersPerDegreeLng = METERS_PER_DEGREE_LAT * Math.cos(latRad);
  const latIndex = Math.round((lat * METERS_PER_DEGREE_LAT) / SQUARE_SIZE_M);
  const lngIndex = Math.round((lng * metersPerDegreeLng) / SQUARE_SIZE_M);
  return `${latIndex},${lngIndex}`;
}

/** Display/copy form: digits only (`1234,5678`), stripping any legacy label prefix. */
export function mapReferenceNumbers(ref: string): string {
  const trimmed = ref.trim();
  const match = trimmed.match(/(-?\d+)\s*,\s*(-?\d+)\s*$/);
  if (match) return `${match[1]},${match[2]}`;
  return trimmed;
}

export function valueStatusLabel(status: PlaceValueStatus): string {
  switch (status) {
    case "coming_soon":
    case "in_progress":
      return PLACE_CARD_FIGURE_STATUS;
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

/** FP1 class chip label — Market / Modelled / Estimate. */
export function placeClassChip(
  tag: PlaceRentTag | PlaceCardClass | string,
): string {
  switch (tag) {
    case "market":
      return PLACE_CARD_CLASS_CHIP.market;
    case "proxy":
      return PLACE_CARD_CLASS_CHIP.proxy;
    case "shadow":
      return PLACE_CARD_CLASS_CHIP.shadow;
    default:
      return PLACE_CARD_CLASS_CHIP.shadow;
  }
}

/**
 * Unit rule (v1): ≥20 dwellings → typical home; &lt;20 (incl. 0) → too few homes.
 * Never present a 0 figure. Explicit `card_state: "no_homes"` stays a separate path.
 */
export function placeUnitKind(
  dwellings: number | null | undefined,
): PlaceUnitKind {
  if (dwellings == null || !Number.isFinite(dwellings)) {
    return "typical_home";
  }
  if (dwellings < PLACE_CARD_MIN_DWELLINGS_TYPICAL) {
    return "too_few_homes";
  }
  return "typical_home";
}

/**
 * Sales-basis line (item 5) — only when the API sends all three fields.
 * No Medium / year-window defaults; missing fields hide the line.
 */
export function placeSalesBasisLine(
  from: number | null | undefined,
  to: number | null | undefined,
  confidence: PlaceCardConfidence | null | undefined,
): string | null {
  if (
    from == null ||
    to == null ||
    !Number.isFinite(from) ||
    !Number.isFinite(to) ||
    confidence == null
  ) {
    return null;
  }
  return `Based on local home sales (${from}–${to}). How sure we are: ${confidence}`;
}

/** Value classes that may apply — plain words; no £. */
export function defaultAgrRows(): PlaceAgrRow[] {
  return defaultAgrGroupRows() as PlaceAgrRow[];
}

export function deriveHolder(card: PlaceCardPayload): PlaceHolder {
  if (card.holder) return card.holder;
  const community = card.community_ownership;
  if (community?.on_this_point && (community.assets?.length ?? 0) > 0) {
    const name = community.assets?.[0]?.name?.trim();
    return {
      status: "public_record",
      label: name || "Community ownership (public record)",
      note: community.note || undefined,
    };
  }
  const publicCrown = card.public_or_crown;
  if (publicCrown?.on_this_point && (publicCrown.holdings?.length ?? 0) > 0) {
    const org = publicCrown.holdings?.[0]?.organisation?.trim();
    return {
      status: "public_record",
      label: org || "Public / Crown holding (public record)",
      note: publicCrown.note || undefined,
    };
  }
  return {
    status: "private_not_shown",
    label: "private, not shown",
    note: "Owner details from public records only.",
  };
}

/** Demo fixture for internal preview / e2e — DZ2022 (not 2011). */
export const PLACE_CARD_FIXTURE: PlaceCardPayload = {
  contract: "place_card_v1",
  lat: 55.8642,
  lng: -4.2518,
  place_label: "Glasgow City Centre",
  postcode: "G2 1DU",
  council_code: "S12000049",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
    zones: [
      {
        code: "S01014567",
        vintage: 2022,
        name: "City Centre South",
        on_boundary: false,
      },
    ],
  },
  intermediate_zone: {
    status: "ok",
    code: "S02002645",
    name: "City Centre",
  },
  square_reference: scotLandSquareReference(55.8642, -4.2518),
  dwellings: 410,
  // Demo fixture only — public API must send these; sanitize does not invent them.
  sales_year_from: 2019,
  sales_year_to: 2023,
  confidence: "Medium",
  agr_rows: defaultAgrRows(),
  constraints: [
    { id: "flood", label: "Flood", applies: false },
    { id: "sssi", label: "SSSI", applies: false },
    { id: "crofting", label: "Crofting", applies: false },
  ],
  holder: {
    status: "private_not_shown",
    label: "private, not shown",
  },
  vacant_or_derelict: false,
  flags: ["registered_cadastre"],
  parcel: {
    found: true,
    label: "GLA12345",
    inspire_id: "inspire-demo",
    area_sqm: 240,
    note: "INSPIRE parcel is an indicative registered extent, not a title sheet.",
  },
  public_or_crown: {
    on_this_point: false,
    holdings: [],
    note: "Five national bodies only. Not local-authority land.",
    map_url:
      "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
  },
  common_good: {
    status: "linked",
    register: {
      url: "https://www.glasgow.gov.uk/",
      label: "Glasgow Common Good register",
    },
    national_gap: "No national open Common Good map layer.",
  },
  private_or_sasine: {
    status: "gap",
    note: "Private names and Sasine extents stay on ScotLIS / paid products.",
  },
  land_register_outline: { status: "inside_outline" },
  land_outline: {
    status: "inside_outline",
    label: "Land outline",
    area_sqm: 240,
    note: "Registered extent outline only — not a title sheet.",
  },
  layers: [
    {
      id: "boundaries",
      label: "ROS INSPIRE parcels",
      status: "live",
      intersects: true,
      note: "INSPIRE parcel is an indicative registered extent, not a title sheet.",
      source_url: "https://www.ros.gov.uk/open-data",
      licence: "Licensed under the Open Government Licence v3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      detail: { label: "GLA12345", inspire_id: "inspire-demo", area_sqm: 240 },
    },
    {
      id: "vdl",
      label: "Vacant and derelict land",
      status: "live",
      intersects: false,
      source_url:
        "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      detail: { sites: [] },
    },
    {
      id: "public_crown",
      label: "Public and Crown Estate land",
      status: "gap",
      intersects: null,
      note:
        "SG 2024 dashboard only — licence unverified/not open. Not on the public map.",
      source_url:
        "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
      licence: "unverified/not open",
    },
    {
      id: "common_good",
      label: "Common Good",
      status: "linked",
      intersects: null,
      note: "No national open Common Good map layer.",
      source_url: "https://www.glasgow.gov.uk/",
      licence:
        "Linked registers; Highland licence unconfirmed; Fife OS INSPIRE EUL linked only",
    },
    {
      id: "la_holdings",
      label: "Local-authority land holdings",
      status: "gap",
      intersects: null,
      note: "National LA ownership layer is not openly licensed for this portal.",
      source_url: "https://data.spatialhub.scot/dataset/land_ownership-is",
      licence: "Not openly licensed for this portal",
    },
    {
      id: "sasine_private",
      label: "Private owners and Sasine land",
      status: "gap",
      intersects: null,
      note: "Private names and Sasine extents stay on ScotLIS / paid products.",
      source_url: "https://scotlis.ros.gov.uk/",
      licence: "Incomplete or paid — gaps shown, names not invented",
    },
  ],
  links: [
    {
      id: "scotlis",
      label: "Official title on ScotLIS",
      url: "https://scotlis.ros.gov.uk/",
    },
    {
      id: "methodology",
      label: PLACE_CARD_HOW_WE_WORK_LABEL,
      url: "/methodology",
    },
  ],
  scotlis: {
    public_home: "https://scotlis.ros.gov.uk/",
    label: "Official title on ScotLIS",
    note: "ScotLIS is Registers of Scotland’s official land information service.",
    search_hint: "G2 1DU",
  },
};

/** place_card_v1 miss payload for a point outside Scotland's land map (SW-019). */
export function outsideScotlandPlaceCard(
  lat: number,
  lng: number,
): PlaceCardPayload {
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: null,
    council_name: null,
    data_zone: {
      status: "miss",
      code: null,
      name: null,
      vintage: null,
      note: PLACE_CARD_OUT_OF_SCOTLAND_LINE,
    },
    intermediate_zone: { status: "no_data", name: null, note: null },
    square_reference: scotLandSquareReference(lat, lng),
    agr_rows: defaultAgrRows(),
    constraints: [],
    layers: [],
    links: [],
  };
}

/**
 * Public place card for a map point.
 * SW-019: `/platform/place` and `/api/place.json` 400 "outside Scotland"
 * become a sea-miss card so the spinner clears and the plain line shows.
 */
export async function fetchPlaceCard({
  lat,
  lng,
  postcode,
}: FetchPlaceCardArgs): Promise<PlaceCardPayload> {
  const params = new URLSearchParams({
    lat: String(lat),
    lng: String(lng),
  });
  if (postcode) params.set("postcode", postcode);
  try {
    return await apiJson<PlaceCardPayload>(
      `/platform/place?${params.toString()}`,
    );
  } catch (err) {
    if (isOutsideScotlandError(err)) {
      return outsideScotlandPlaceCard(lat, lng);
    }
    throw err;
  }
}

/** Map stable agr row ids → approved RENT_GROUP_NAMES (never Surface/Resource/Nature). */
const AGR_ROW_LABEL_BY_ID: Record<string, string> = {
  surface: RENT_GROUP_NAME.land,
  resource: RENT_GROUP_NAME.resources,
  nature: RENT_GROUP_NAME.nature,
};

/** Legacy API/fixture labels → approved headings (defence in depth). */
const AGR_ROW_LABEL_BY_LEGACY: Record<string, string> = {
  Surface: RENT_GROUP_NAME.land,
  Resource: RENT_GROUP_NAME.resources,
  Nature: RENT_GROUP_NAME.nature,
};

const AGR_ROW_GLOSS_BY_ID: Record<string, string> = {
  surface: PLACE_CARD_PART_GLOSS.land,
  resource: PLACE_CARD_PART_GLOSS.resources,
  nature: PLACE_CARD_PART_GLOSS.nature,
};

function normalizeAgrRow(row: PlaceAgrRow): PlaceAgrRow {
  const legacyAmount = (row as PlaceAgrRow & { amount_label?: string })
    .amount_label;
  const status: PlaceValueStatus =
    row.status === "in_progress" || row.status === "coming_soon"
      ? row.status
      : legacyAmount
        ? "in_progress"
        : "coming_soon";
  const approved =
    AGR_ROW_LABEL_BY_ID[row.id] ??
    AGR_ROW_LABEL_BY_LEGACY[row.label] ??
    row.label;
  const classTag: PlaceRentTag =
    row.class === "market" ||
    row.class === "proxy" ||
    row.class === "shadow"
      ? row.class
      : row.tag === "market" || row.tag === "proxy" || row.tag === "shadow"
        ? row.tag
        : "shadow";
  return {
    ...row,
    label: approved,
    gloss: row.gloss?.trim() || AGR_ROW_GLOSS_BY_ID[row.id] || null,
    range: row.range?.trim() || PLACE_CARD_PART_NOT_YET,
    unit: row.unit ?? null,
    confidence: row.confidence ?? null,
    method: row.method ?? null,
    class: classTag,
    tag: classTag,
    status,
    applies: row.applies !== false,
    of_which: (row.of_which || []).filter(
      (note) => note.id !== "infrastructure_share",
    ),
  };
}

/** Strip any accidental AGR £ payload before render; fill Designer defaults. */
export function sanitizePlaceCard(payload: PlaceCardPayload): PlaceCardPayload {
  const { agr: _agr, ...rest } = payload;
  const zone = preferDz2022(rest.data_zone);
  const agrRows = (rest.agr_rows?.length ? rest.agr_rows : defaultAgrRows())
    .map(normalizeAgrRow)
    .filter((row) => row.applies !== false);
  // Pass through every constraint row (true / false / null). Empty means a gap.
  const constraints = Array.isArray(rest.constraints) ? rest.constraints : [];
  const iz = rest.intermediate_zone;
  const izCode = iz?.code ? String(iz.code) : null;
  const izName = iz?.name?.trim() || null;
  const intermediate_zone = iz
    ? {
        ...iz,
        // Never show "No data" when the IZ code is known.
        note:
          izCode && !izName
            ? iz.note?.trim() || PLACE_CARD_NAME_NOT_LOADED
            : iz.note ?? null,
      }
    : {
        status: "no_data",
        name: null,
        note: "No data",
      };
  return {
    ...rest,
    data_zone: zone,
    square_reference: mapReferenceNumbers(
      rest.square_reference?.trim() ||
        scotLandSquareReference(rest.lat, rest.lng),
    ),
    agr_rows: agrRows,
    constraints,
    holder: deriveHolder(rest),
    intermediate_zone,
    // Pass through only — never invent sales years or confidence.
    sales_year_from: rest.sales_year_from ?? null,
    sales_year_to: rest.sales_year_to ?? null,
    confidence: rest.confidence ?? null,
    fully_estimated: Boolean(rest.fully_estimated),
    // GBP-LIVE: pass through flag + display; never invent money here.
    gbp_live: rest.gbp_live ?? { enabled: false },
    surface_rent_display: rest.surface_rent_display ?? null,
  };
}
