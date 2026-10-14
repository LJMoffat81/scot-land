/**
 * Public place-card contract (place_card_v1).
 * Ledger redesign IA — value / limits sections; DZ2022; no £ figures.
 */

import { apiJson } from "./api";

/** Public figures withheld — keep exact wording. */
export const PLACE_CARD_FIGURES_CHECKED =
  "Figures are being checked and aren't published yet";

export const PLACE_CARD_RESEARCH_DISCLAIMER =
  "research estimate, not an official valuation or bill";

export const PLACE_CARD_CONSTRAINT_LABEL =
  "Constraint: changes best use, adds no value";

export const PLACE_CARD_HOW_WE_VALUE_LABEL = "How we value land";

export type PlaceRentTag = "market" | "proxy" | "shadow";

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

export type PlaceDataZone = {
  status: "ok" | "miss" | "unavailable" | string;
  code?: string | null;
  name?: string | null;
  vintage?: number | null;
  zones?: Array<{
    code: string;
    vintage: number;
    name?: string | null;
    on_boundary?: boolean;
  }>;
  note?: string | null;
  reasons?: string[];
};

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
  /** Public status — never a £ amount. */
  status: PlaceValueStatus;
  /** When false, row is omitted from the place card. */
  applies?: boolean;
  of_which?: Array<{ id: string; label: string }>;
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
  /** Scot-LAND square reference — never a what3words brand string. */
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
};

export type FetchPlaceCardArgs = {
  lat: number;
  lng: number;
  postcode?: string | null;
};

const METERS_PER_DEGREE_LAT = 111_320.0;
const SQUARE_SIZE_M = 3.0;

/** Scot-LAND square reference from snapped 3×3 m grid (no what3words brand). */
export function scotLandSquareReference(lat: number, lng: number): string {
  const latRad = (lat * Math.PI) / 180;
  const metersPerDegreeLng = METERS_PER_DEGREE_LAT * Math.cos(latRad);
  const latIndex = Math.round((lat * METERS_PER_DEGREE_LAT) / SQUARE_SIZE_M);
  const lngIndex = Math.round((lng * metersPerDegreeLng) / SQUARE_SIZE_M);
  return `Scot-LAND square reference ${latIndex},${lngIndex}`;
}

export function valueStatusLabel(status: PlaceValueStatus): string {
  switch (status) {
    case "coming_soon":
      return "Coming soon";
    case "in_progress":
      return "In progress";
    default: {
      const _exhaustive: never = status;
      return _exhaustive;
    }
  }
}

/** Value classes that may apply — plain words; no £. */
export function defaultAgrRows(): PlaceAgrRow[] {
  return [
    {
      id: "surface",
      label: "Surface land",
      tag: "proxy",
      status: "in_progress",
      applies: true,
      of_which: [
        { id: "planning_uplift", label: "of which: planning uplift" },
      ],
    },
    {
      id: "resource",
      label: "Resources from the land and sea",
      tag: "market",
      status: "coming_soon",
      applies: true,
    },
    {
      id: "nature",
      label: "Nature that has no market price",
      tag: "shadow",
      status: "coming_soon",
      applies: true,
    },
  ];
}

/**
 * Constraints listed when they apply (or when status is unknown for honesty).
 * Flood, SSSI, crofting are the redesign focus.
 */
export function defaultConstraints(
  vacantOrDerelict?: boolean,
): PlaceConstraintRow[] {
  return [
    {
      id: "flood",
      label: "Flood",
      applies: null,
      note: "No data",
    },
    {
      id: "sssi",
      label: "SSSI",
      applies: null,
      note: "No data",
    },
    {
      id: "crofting",
      label: "Crofting",
      applies: null,
      note: "No data",
    },
    ...(vacantOrDerelict
      ? [
          {
            id: "vdl",
            label: "Vacant and derelict land",
            applies: true as boolean | null,
          },
        ]
      : []),
  ];
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

/**
 * Prefer a real DZ2022 entry from `zones[]` when present.
 * Never invent vintage 2022 — keep API vintage (2011 / null) otherwise.
 */
export function preferDz2022(zone: PlaceDataZone | null | undefined): PlaceDataZone | null {
  if (!zone) return null;
  const zones = zone.zones ?? [];
  const dz2022 = zones.find((z) => z.vintage === 2022);
  if (dz2022) {
    return {
      ...zone,
      status: "ok",
      code: dz2022.code,
      name: dz2022.name ?? zone.name,
      vintage: 2022,
    };
  }
  return zone;
}

/** Place-card Data Zone field heading — never label an S01 2011 code as 2022. */
export function dataZoneFieldLabel(
  vintage: number | null | undefined,
): string {
  if (vintage === 2022) return "Data zone (2022)";
  if (vintage === 2011) return "Data zone (2011)";
  return "Data zone";
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
      label: PLACE_CARD_HOW_WE_VALUE_LABEL,
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

export function fetchPlaceCard({
  lat,
  lng,
  postcode,
}: FetchPlaceCardArgs): Promise<PlaceCardPayload> {
  const params = new URLSearchParams({
    lat: String(lat),
    lng: String(lng),
  });
  if (postcode) params.set("postcode", postcode);
  return apiJson<PlaceCardPayload>(`/platform/place?${params.toString()}`);
}

function normalizeAgrRow(row: PlaceAgrRow): PlaceAgrRow {
  const legacyAmount = (row as PlaceAgrRow & { amount_label?: string })
    .amount_label;
  const status: PlaceValueStatus =
    row.status === "in_progress" || row.status === "coming_soon"
      ? row.status
      : legacyAmount
        ? "in_progress"
        : "coming_soon";
  return {
    ...row,
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
  return {
    ...rest,
    data_zone: zone,
    square_reference:
      rest.square_reference?.trim() ||
      scotLandSquareReference(rest.lat, rest.lng),
    agr_rows: agrRows,
    constraints,
    holder: deriveHolder(rest),
    intermediate_zone: rest.intermediate_zone ?? {
      status: "no_data",
      name: null,
      note: "No data",
    },
  };
}
