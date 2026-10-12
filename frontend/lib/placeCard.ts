/**
 * Public place-card contract (place_card_v1).
 * Mirrors GET /platform/place — no modelled AGR £.
 */

import { apiJson } from "./api";

export type PlaceLayerStatus = "live" | "linked" | "gap" | string;

export type PlaceLayer = {
  id: string;
  label: string;
  status: PlaceLayerStatus;
  intersects: boolean | null;
  note?: string | null;
  source_url?: string | null;
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

export type PlaceCardPayload = {
  contract: "place_card_v1" | string;
  lat: number;
  lng: number;
  postcode?: string | null;
  council_code?: string | null;
  council_name?: string | null;
  data_zone?: PlaceDataZone | null;
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

/** Demo fixture for standalone preview / e2e (no live network). */
export const PLACE_CARD_FIXTURE: PlaceCardPayload = {
  contract: "place_card_v1",
  lat: 55.8642,
  lng: -4.2518,
  postcode: "G2 1DU",
  council_code: "S12000049",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01010264",
    name: "City Centre South",
    vintage: 2011,
    zones: [
      {
        code: "S01010264",
        vintage: 2011,
        name: "City Centre South",
        on_boundary: false,
      },
    ],
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
      detail: { label: "GLA12345", inspire_id: "inspire-demo", area_sqm: 240 },
    },
    {
      id: "vdl",
      label: "Vacant and derelict land",
      status: "live",
      intersects: false,
      source_url:
        "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
      detail: { sites: [] },
    },
    {
      id: "public_crown",
      label: "Public and Crown Estate land",
      status: "live",
      intersects: false,
      note: "Five national bodies only. Not local-authority land.",
      source_url:
        "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
      detail: { holdings: [] },
    },
    {
      id: "common_good",
      label: "Common Good",
      status: "linked",
      intersects: null,
      note: "No national open Common Good map layer.",
      source_url: "https://www.glasgow.gov.uk/",
    },
    {
      id: "la_holdings",
      label: "Local-authority land holdings",
      status: "gap",
      intersects: null,
      note: "National LA ownership layer is not openly licensed for this portal.",
      source_url:
        "https://data.spatialhub.scot/dataset/land_ownership-is",
    },
    {
      id: "sasine_private",
      label: "Private owners and Sasine land",
      status: "gap",
      intersects: null,
      note: "Private names and Sasine extents stay on ScotLIS / paid products.",
      source_url: "https://scotlis.ros.gov.uk/",
    },
  ],
  links: [
    {
      id: "scotlis",
      label: "Official title on ScotLIS",
      url: "https://scotlis.ros.gov.uk/",
    },
    {
      id: "public_land_map",
      label: "Scottish public and Crown Estate land map",
      url: "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
    },
    {
      id: "common_good_register",
      label: "Glasgow Common Good register",
      url: "https://www.glasgow.gov.uk/",
    },
    {
      id: "vdl_register",
      label: "SVDLS site register",
      url: "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
    },
    {
      id: "methodology",
      label: "Sources and method",
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

/** Strip any accidental AGR payload before render. */
export function sanitizePlaceCard(payload: PlaceCardPayload): PlaceCardPayload {
  const { agr: _agr, ...rest } = payload;
  return rest;
}
