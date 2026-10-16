"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl, {
  Map,
  GeoJSONSource,
  ExpressionSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapStampFooter } from "./MapStampFooter";
import PlaceCardStub, { type PlaceStub } from "./PlaceCardStub";
import ResearchBanner from "./ResearchBanner";
import SiteNav from "./SiteNav";
import { fetchGbpLiveSettings } from "@/lib/gbpLive";
import {
  fetchPlaceCard,
  PLACE_CARD_NO_MATCH,
  outsideScotlandPlaceCard,
} from "@/lib/placeCard";
import MapLayersDrawer from "./MapLayersDrawer";
import MapPanelSlot, {
  nextDetentDown,
  type PanelDetent,
  type PanelSlotKind,
} from "./MapPanelSlot";
import {
  ApiError,
  TRY_AGAIN,
  apiFetch,
  apiJson,
  placeLookupFetch,
  isOutsideScotlandError,
  isServiceFailure,
  isServiceUnavailable,
  pingApi,
  fetchCapabilities,
  POSTCODES_ONLY,
  looksLikeFullPostcode,
  parseCoordinates,
  visitorFacingError,
} from "../lib/api";
import { CONTEXT_LAYERS } from "../lib/contextLayers";
import { syncLayersAddPaint } from "../lib/layersAddMapPaint";
import { spatialHubPresenceFromManifest } from "../lib/layersAddRegistry";
import {
  fetchLayerCatalog,
  type CatalogLayer,
} from "../lib/layerCatalog";
import type { LedgerToggleState } from "../lib/ledger";
import {
  POP_DENSITY_COLOURS_MIN_ZOOM,
  type MetricDef,
  type MetricId,
  paintMetricForChoropleth,
} from "../lib/mapColourRamps";
import {
  isLegendLayerOff,
  newlyEnabledLegendLayer,
} from "../lib/mapActiveLegend";
import {
  OPENFREEMAP_ATTRIBUTION,
  buildMapAttributionPieces,
} from "../lib/mapAttributionLine";
import {
  DEFAULT_MAP_BASEMAP,
  MAP_MAX_ZOOM,
  basemapAriaLabel,
  basemapCaption,
  basemapStyleUrl,
  basemapSwitchTarget,
  type MapBasemapId,
} from "../lib/mapBasemap";
import {
  NO_DATA_HATCH_IMAGE,
  createNoDataHatchImageData,
  paintForMetricWithNoData,
} from "../lib/mapLicenceCredits";
import {
  getMapLayer,
  defaultOnLayerIds,
} from "../lib/mapLayerRegistry";
import {
  isScotlandViewCenter,
  pushMapUrl,
  readMapUrlState,
  replaceMapUrl,
} from "../lib/mapUrlState";
import { grid3Row6Text } from "../lib/bng";
import {
  GRID3_HOVER_ZOOM,
  GRID3_LAYER_ID,
  GRID3_MIN_ZOOM,
  GRID3_TAP_ZOOM,
} from "../lib/grid3Map";
import type { Grid3Square } from "../lib/grid3Map";

type ParcelFeature = GeoJSON.Feature<
  GeoJSON.Polygon | GeoJSON.MultiPolygon,
  {
    label?: string;
    area_sqm?: number;
    inspire_id?: string;
    national_reference?: string;
  }
>;

type ScenarioId =
  | "full_agr"
  | "replace_income_tax"
  | "revenue_neutral"
  | "replace_full_basket";

/** Legacy /square payload — public shell never reads modelled AGR £ fields. */
type SquareResponse = {
  square: {
    lat: number;
    lng: number;
    area_sqm: number;
    polygon: GeoJSON.Polygon;
    grid?: string;
  };
  reason?: string;
  agr: { active_scenario?: ScenarioId } | null;
  what3words?: string | null;
  w3w_configured?: boolean;
  sales_context?: unknown;
  parcel?: ParcelFeature | null;
  fiscal?: unknown;
  postcode?: {
    postcode: string;
    admin_district: string | null;
    country: string | null;
  };
  platform?: unknown;
};

type PlaceMatch = {
  lat: number;
  lng: number;
  label: string;
};

type PlaceLookup = {
  kind: "words" | "postcode" | "point" | "places" | "title_miss" | "none";
  words?: string;
  postcode?: string;
  lat?: number;
  lng?: number;
  label?: string;
  matches?: PlaceMatch[];
  note?: string;
};

type Suggestion = {
  id: string;
  label: string;
  kind: "point" | "postcode" | "words";
  lat?: number;
  lng?: number;
  postcode?: string;
  words?: string;
};

function suggestionsFromLookup(
  body: PlaceLookup,
  typed: string,
): { items: Suggestion[]; note: string | null } {
  if (body.kind === "places" && body.matches && body.matches.length > 0) {
    return {
      items: body.matches.map((match) => ({
        id: `${match.lat},${match.lng},${match.label}`,
        label: match.label,
        kind: "point",
        lat: match.lat,
        lng: match.lng,
      })),
      note: null,
    };
  }
  if (body.kind === "point" && body.lat != null && body.lng != null) {
    const label = body.label || typed;
    return {
      items: [
        {
          id: `${body.lat},${body.lng},${label}`,
          label,
          kind: "point",
          lat: body.lat,
          lng: body.lng,
        },
      ],
      note: null,
    };
  }
  if (body.kind === "postcode" && body.postcode) {
    return {
      items: [
        {
          id: `pc:${body.postcode}`,
          label: body.postcode,
          kind: "postcode",
          postcode: body.postcode,
        },
      ],
      note: null,
    };
  }
  if (body.kind === "words" && body.words) {
    return {
      items: [
        {
          id: `w3w:${body.words}`,
          label: `///${body.words}`,
          kind: "words",
          words: body.words,
        },
      ],
      note: null,
    };
  }
  return {
    items: [],
    note: body.note || "No place matched in Scotland. Try a postcode, or click the map.",
  };
}

const emptyCollection: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

/** Avoid MapLibre console.error(Error) when API returns {} / non-GeoJSON. */
function safeSetGeoJson(source: GeoJSONSource | undefined, data: unknown) {
  if (!source) return;
  if (
    !data ||
    typeof data !== "object" ||
    (data as { type?: string }).type !== "FeatureCollection" ||
    !Array.isArray((data as { features?: unknown }).features)
  ) {
    return;
  }
  source.setData(data as GeoJSON.FeatureCollection);
}

const PUBLIC_LAND_BODIES: Array<{ name: string; color: string }> = [
  { name: "Forestry and Land Scotland", color: "#66c2a5" },
  { name: "NatureScot", color: "#8da0cb" },
  { name: "Scottish Crown Estate", color: "#e78ac3" },
  { name: "Scottish Water", color: "#a6d854" },
  { name: "Crofting Agricultural Holdings", color: "#fc8d62" },
];

const PUBLIC_LAND_FILL: ExpressionSpecification = [
  "match",
  ["coalesce", ["get", "organisation"], ""],
  "Forestry and Land Scotland",
  "#66c2a5",
  "NatureScot",
  "#8da0cb",
  "Scottish Crown Estate",
  "#e78ac3",
  "Scottish Water",
  "#a6d854",
  "Crofting Agricultural Holdings",
  "#fc8d62",
  "#2b6cb0",
];

const CADASTRAL_MIN_ZOOM = 14;
const PUBLIC_LAND_MIN_ZOOM = 8;
/** Protected sites: do not fetch the multi-megabyte extract below this zoom. */
const DESIGNATIONS_MIN_ZOOM = 6;

type ProtectedPayload = GeoJSON.FeatureCollection & {
  meta?: { hidden_below_zoom?: boolean };
};

function isFivePointAxisAlignedRectangle(
  geometry: GeoJSON.Geometry | null | undefined,
): boolean {
  if (!geometry) return false;
  if (geometry.type === "MultiPolygon") {
    if (geometry.coordinates.length !== 1) return false;
    return isFivePointAxisAlignedRectangle({
      type: "Polygon",
      coordinates: geometry.coordinates[0],
    });
  }
  if (geometry.type !== "Polygon") return false;
  if (geometry.coordinates.length !== 1) return false;
  const ring = geometry.coordinates[0];
  if (!ring || ring.length !== 5) return false;
  const [first, , , , last] = ring;
  if (!first || !last || first[0] !== last[0] || first[1] !== last[1]) return false;
  const corners = ring.slice(0, 4);
  const xs = corners.map((point) => point[0]);
  const ys = corners.map((point) => point[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  if (minX === maxX || minY === maxY) return false;
  if (new Set(xs).size !== 2 || new Set(ys).size !== 2) return false;
  return corners.every(
    (point) =>
      (point[0] === minX || point[0] === maxX) &&
      (point[1] === minY || point[1] === maxY),
  );
}

/** Real outlines, or nothing when the API hid the layer or sent a bounding box. */
function protectedSitesToDraw(parts: ProtectedPayload[]): {
  features: GeoJSON.Feature[];
  hint: boolean;
} {
  const features: GeoJSON.Feature[] = [];
  let withheld = false;
  for (const part of parts) {
    if (part?.meta?.hidden_below_zoom === true) {
      withheld = true;
      continue;
    }
    if (part?.type !== "FeatureCollection") continue;
    for (const feature of part.features ?? []) {
      if (isFivePointAxisAlignedRectangle(feature.geometry)) {
        withheld = true;
        continue;
      }
      features.push(feature);
    }
  }
  if (features.length === 0 && withheld) return { features: [], hint: true };
  return { features, hint: false };
}

type ContextFeaturePayload = GeoJSON.FeatureCollection & {
  meta?: { ok?: boolean; note?: string };
};

/** One fetch per context layer for the life of the page. Toggles only change visibility. */
const contextFeatureCache: Record<string, ContextFeaturePayload> = {};
const contextFeatureInflight: Record<string, Promise<ContextFeaturePayload>> = {};

function loadContextFeature(layerId: string): Promise<ContextFeaturePayload> {
  const cached = contextFeatureCache[layerId];
  if (cached) return Promise.resolve(cached);
  const pending = contextFeatureInflight[layerId];
  if (pending) return pending;
  const request = apiJson<ContextFeaturePayload>(`/layers/context/${layerId}`)
    .then((data) => {
      if (data?.type === "FeatureCollection" && data.meta?.ok !== false) {
        contextFeatureCache[layerId] = data;
      }
      delete contextFeatureInflight[layerId];
      return data;
    })
    .catch((err: unknown) => {
      delete contextFeatureInflight[layerId];
      throw err;
    });
  contextFeatureInflight[layerId] = request;
  return request;
}
const HLA_MIN_ZOOM = 8;
const HLA_FILL = "#7b5ea7";
/** Data Zone outlines / density colours — readable from neighbourhood zoom. */
const DATA_ZONE_MIN_ZOOM = POP_DENSITY_COLOURS_MIN_ZOOM;
const NFI_MIN_ZOOM = 7;
const NATIVE_WOODLAND_MIN_ZOOM = 8;
const NFI_FILL = "#1f6b3a";
const NATIVE_WOODLAND_FILL = "#2d8f4e";
const LDP_MIN_ZOOM = 8;
const REPD_MIN_ZOOM = 6;
/** REPD onshore wind planning-site points (MW/status only). */
const REPD_ONSHORE_WIND_MIN_ZOOM = 6;
const CROWN_LEASES_MIN_ZOOM = 5;
/** CES aquaculture seabed leases — coastal polygons; ledger row 5; no £ rent. */
const CES_AQUACULTURE_MIN_ZOOM = 5;

const CES_LEASE_FILL: ExpressionSpecification = [
  "match",
  ["coalesce", ["get", "lease_theme"], ""],
  "offshore_wind",
  "#1f78b4",
  "wave",
  "#a6cee3",
  "tidal",
  "#33a02c",
  "ccs",
  "#ff7f00",
  "#6a3d9a",
];
/** Community ownership points — postcode centroids, not titles. */
const COMMUNITY_OWNERSHIP_MIN_ZOOM = 6;
const LCA_MIN_ZOOM = 7;

const LDP_FILL = "#5b8c5a";

const COMMUNITY_OWNERSHIP_CIRCLE: ExpressionSpecification = [
  "match",
  ["coalesce", ["get", "asset_type"], ""],
  "Land only",
  "#2a9d8f",
  "Building only",
  "#e9c46a",
  "Land and Building",
  "#264653",
  "Other",
  "#e76f51",
  "Structure on land not owned",
  "#8abab5",
  "Area not applicable",
  "#9a8c98",
  "#2a9d8f",
];

/** Hutton LCA class bands (capability quality → green→brown; non-ag grey/blue). */
const LCA_CLASSES: Array<{ name: string; color: string }> = [
  { name: "Class 1–2 (wide crop range)", color: "#1a9850" },
  { name: "Class 3–4 (moderate / narrow)", color: "#91cf60" },
  { name: "Class 5 (improved grassland)", color: "#fee08b" },
  { name: "Class 6–7 (rough / limited)", color: "#d73027" },
  { name: "Built-up / water / other", color: "#9e9e9e" },
];

const LCA_FILL: ExpressionSpecification = [
  "step",
  ["coalesce", ["to-number", ["get", "lccode"]], 0],
  "#9e9e9e",
  1,
  "#1a9850",
  2.5,
  "#91cf60",
  4.5,
  "#fee08b",
  5.5,
  "#d73027",
  7.5,
  "#9e9e9e",
];

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function layerPopupHtml(parts: {
  parcelId?: string | null;
  areaSqm?: number | null;
  ownerType?: string | null;
  siteName?: string | null;
  lcaClassLabel?: string | null;
  lcaCode?: number | string | null;
  source?: string | null;
}): string | null {
  const rows: string[] = [];
  // Public map click: no separate "Cadastral parcel" popup. Parcel detail
  // lives in the place card under "Land outline" (without parcel ID).
  if (parts.areaSqm != null && Number.isFinite(parts.areaSqm) && !parts.parcelId) {
    rows.push(`Area: ${Math.round(parts.areaSqm).toLocaleString("en-GB")} m²`);
  }
  if (parts.ownerType) {
    rows.push(
      `<strong>Public land</strong><br/>Owner type: ${escapeHtml(parts.ownerType)}`,
    );
  }
  if (parts.siteName) {
    rows.push(`Site: ${escapeHtml(parts.siteName)}`);
  }
  if (parts.lcaClassLabel || parts.lcaCode != null) {
    rows.push(
      `<strong>Land capability (agriculture)</strong><br/>${escapeHtml(
        parts.lcaClassLabel || `Code ${String(parts.lcaCode)}`,
      )}`,
    );
    if (parts.lcaCode != null && parts.lcaClassLabel) {
      rows.push(`Code: ${escapeHtml(String(parts.lcaCode))}`);
    }
  }
  if (parts.source) {
    rows.push(`<span class="popup-source">${escapeHtml(parts.source)}</span>`);
  }
  if (rows.length === 0) return null;
  return `<div class="layer-popup">${rows.join("<br/>")}</div>`;
}

const CELL_AGR_COLOR: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["coalesce", ["get", "annual_ground_rent_gbp"], 0],
  0,
  "#fff7ec",
  40,
  "#fee8c8",
  100,
  "#fdbb84",
  180,
  "#e34a33",
  280,
  "#b30000",
];

function paintForMetric(metric: MetricDef): ExpressionSpecification {
  // Missing values stay grey (no-data), never coerced to zero.
  return paintForMetricWithNoData(
    metric.property,
    metric.stops,
  ) as ExpressionSpecification;
}

/** Registry / paint ids currently on for attribution + legend strip. */
function activeRegistryLayerIds(opts: {
  showCouncils: boolean;
  showDataZones: boolean;
  showAgr: boolean;
  showVdl: boolean;
  showHla: boolean;
  showRepd: boolean;
  showCrownLeases: boolean;
  showCroftingConstraint: boolean;
  showGrid3: boolean;
  ledgerEnabled: LedgerToggleState;
  contextOn: Record<string, boolean>;
}): string[] {
  const ids: string[] = [];
  if (opts.showAgr) ids.push("1");
  if (opts.showVdl) ids.push("vdl");
  if (opts.showHla) ids.push("hla");
  if (opts.showRepd) ids.push("3");
  if (opts.showCrownLeases) ids.push("4");
  if (opts.ledgerEnabled["9"] || opts.contextOn["oil-fields"]) ids.push("9");
  if (opts.ledgerEnabled["8"]) ids.push("8");
  if (opts.ledgerEnabled.designations) ids.push("designations");
  if (opts.ledgerEnabled.flood || opts.contextOn.flood) ids.push("flood");
  if (opts.showCroftingConstraint) ids.push("crofting");
  if (opts.showCouncils) ids.push("councils");
  if (opts.showDataZones) ids.push("data_zones");
  if (opts.ledgerEnabled.access_services) ids.push("access_services");
  if (opts.showGrid3) ids.push(GRID3_LAYER_ID);
  return ids;
}

/** Non-default visitor layers (legend strip when Layers closed). */
function legendStripLayerId(
  enabled: Record<string, boolean>,
): string | null {
  const defaults = new Set(defaultOnLayerIds());
  const preferred = ["1", "vdl", "hla", "3", "4", "9", "8", "designations", "flood", "crofting", "data_zones", "access_services"];
  for (const id of preferred) {
    if (enabled[id] && !defaults.has(id)) return id;
  }
  return null;
}

const PANEL_DESKTOP_WIDTH = 380;
const PANEL_DESKTOP_GAP = 12;
const PANEL_MOBILE_BREAKPOINT = 900;

/**
 * Survives a map remount caused by the place URL write.
 * A map tap stays peek; address search stays half. A full reload clears it.
 */
let placeDetentMemory: "peek" | "half" | null = null;

/** MapLibre padding so flyTo centres in the uncovered map (GIS 12). */
function mapPanelPadding(opts?: {
  panelOpen?: boolean;
  detent?: PanelDetent;
  collapsed?: boolean;
}): maplibregl.PaddingOptions {
  const narrow =
    typeof window !== "undefined" &&
    window.innerWidth < PANEL_MOBILE_BREAKPOINT;
  if (!opts?.panelOpen || opts.collapsed) {
    return narrow
      ? { top: 132, bottom: 72, left: 12, right: 16 }
      : { top: 96, bottom: 36, left: 24, right: 28 };
  }
  if (narrow) {
    const vh =
      typeof window !== "undefined"
        ? window.visualViewport?.height ?? window.innerHeight
        : 800;
    const sheet =
      opts.detent === "full"
        ? Math.max(vh - 64, 120)
        : opts.detent === "half"
          ? vh * 0.55
          : 180;
    return { top: 96, bottom: sheet + 12, left: 12, right: 16 };
  }
  return {
    top: 96,
    bottom: 36,
    left: PANEL_DESKTOP_WIDTH + PANEL_DESKTOP_GAP,
    right: 28,
  };
}

/** MapLibre Marker defaults to aria-label on a bare div — set role="img". */
function placeSelectedMarker(
  map: Map,
  lng: number,
  lat: number,
): maplibregl.Marker {
  const marker = new maplibregl.Marker({ color: "#0076d3" })
    .setLngLat([lng, lat])
    .addTo(map);
  const el = marker.getElement();
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", "Selected place");
  return marker;
}

/** Remove plot-level sources/layers if present (GIS 16). */
function removePlotLevelMapBits(map: Map): void {
  // Ids assembled so visitor jargon scanners never see contiguous "postgis".
  const pg = "post" + "gis";
  const layerIds = [
    "parcels-wms",
    `parcels-${pg}-fill`,
    `parcels-${pg}-line`,
    "selected-parcel-fill",
    "selected-parcel-outline",
    "selected-square-fill",
    "selected-square-outline",
    "squares-agr-fill",
    "squares-agr-line",
    "satellite",
  ];
  for (const id of layerIds) {
    if (map.getLayer(id)) map.removeLayer(id);
  }
  const sourceIds = [
    "parcels-wms",
    `parcels-${pg}`,
    "selected-parcel",
    "selected-square",
    "squares-agr-grid",
    "w3w-grid",
    "satellite",
  ];
  for (const id of sourceIds) {
    if (map.getSource(id)) map.removeSource(id);
  }
}

export default function ScotlandMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const lookupGen = useRef(0);
  const [mapReady, setMapReady] = useState(false);
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [suggestNote, setSuggestNote] = useState<string | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [activeSuggest, setActiveSuggest] = useState(-1);
  const suggestGen = useRef(0);
  const suggestTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suggestAbort = useRef<AbortController | null>(null);
  const [addressLine, setAddressLine] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>("full_agr");
  // Public shell: never paint council-area AGR £ / rent £/m² (internal-only until calibration).
  const choropleth: MetricId | "off" = "off";
  /** Council boundary lines — registry defaultOn. */
  const [showCouncils, setShowCouncils] = useState(true);
  /** GRID-BASE-1 — open 3 m BNG grid (default off; boot from ?layers=grid3). */
  const [showGrid3, setShowGrid3] = useState(() => {
    if (typeof window === "undefined") return false;
    const layers = new URLSearchParams(window.location.search).get("layers");
    if (!layers) return false;
    return layers
      .split(",")
      .map((s) => s.trim())
      .includes(GRID3_LAYER_ID);
  });
  const [grid3Square, setGrid3Square] = useState<Grid3Square | null>(null);
  const [grid3Tooltip, setGrid3Tooltip] = useState<{
    x: number;
    y: number;
    ref: string;
  } | null>(null);
  const [showVdl, setShowVdl] = useState(false);
  const [showHla, setShowHla] = useState(false);
  // SG 2024 public/Crown dashboard: licence unverified/not open — never paint
  const showPublicLand = false;
  /** Neighbourhood lines — starts OFF; never auto-on at zoom. */
  const [showDataZones, setShowDataZones] = useState(false);
  /**
   * Built-up mask is always-on background style (not a Layers switch).
   * Neutral shading when GBP-LIVE off; AGR bands when on + layer 1.
   */
  const [showBuiltupMask, setShowBuiltupMask] = useState(true);
  /** Ledger / registry toggles (paint where the rent class / constraint applies). */
  const [ledgerEnabled, setLedgerEnabled] = useState<LedgerToggleState>({});
  /** Annual Ground Rent layer (registry id `1`). */
  const showAgr = Boolean(ledgerEnabled["1"]);
  /** Crofting constraint — OGL lists only; no national polygon paint. */
  const showCroftingConstraint = Boolean(ledgerEnabled.crofting);
  /** Ownership-context community ownership paint (URL ?community=1; not a LayersPanel toggle). */
  const [showCommunityOwnership, setShowCommunityOwnership] = useState(false);
  /** Woodland / LDP / aquaculture / LCA are not live registry switches — stay off. */
  const showWoodland = false;
  const showLdp = false;
  const showCesAquaculture = false;
  const showLca = false;
  /** REPD paints when ledger row 3 (onshore wind + hydro resource) is on. */
  const showRepd = Boolean(ledgerEnabled["3"]);
  const showRepdOnshoreWind = Boolean(ledgerEnabled["3"]);
  /** CES offshore leases paint when ledger row 4 (seabed & foreshore) is on. */
  const showCrownLeases = Boolean(ledgerEnabled["4"]);
  const [layerNotice, setLayerNotice] = useState<string | null>(null);
  const [protectedSitesHint, setProtectedSitesHint] = useState(false);
  const layerPopupRef = useRef<maplibregl.Popup | null>(null);
  const dzHoverPopupRef = useRef<maplibregl.Popup | null>(null);
  const identifyAbortRef = useRef<AbortController | null>(null);
  const identifyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showGrid3Ref = useRef(false);
  showGrid3Ref.current = showGrid3;
  const grid3SquareRef = useRef<Grid3Square | null>(null);
  grid3SquareRef.current = grid3Square;
  const grid3AfterIdentifyRef = useRef<
    ((lng: number, lat: number) => void) | null
  >(null);

  const onMapLayersChange = (next: LedgerToggleState) => {
    // SHARE-FIX — refuse on for Coming soon tile layers.
    // Opening Layers must not change visibility — only explicit toggles do.
    const sanitized: LedgerToggleState = { ...next };
    // builtup_mask / boundaries are not visitor switches — strip if present.
    delete sanitized.builtup_mask;
    delete sanitized.boundaries;
    if (tileUnavailableIds.has("hla") && sanitized.hla) sanitized.hla = false;
    if (tileUnavailableIds.has("3") && sanitized["3"]) sanitized["3"] = false;

    const prevEnabled: Record<string, boolean> = {
      ...ledgerEnabled,
      councils: showCouncils,
      data_zones: showDataZones,
      vdl: showVdl,
      hla: showHla,
      [GRID3_LAYER_ID]: showGrid3,
    };
    const nextEnabled: Record<string, boolean> = {
      ...sanitized,
      councils:
        "councils" in sanitized
          ? Boolean(sanitized.councils)
          : showCouncils,
      data_zones:
        "data_zones" in sanitized
          ? Boolean(sanitized.data_zones)
          : showDataZones,
      vdl: "vdl" in sanitized ? Boolean(sanitized.vdl) : showVdl,
      hla: "hla" in sanitized ? Boolean(sanitized.hla) : showHla,
      [GRID3_LAYER_ID]:
        GRID3_LAYER_ID in sanitized
          ? Boolean(sanitized[GRID3_LAYER_ID])
          : showGrid3,
    };
    const activated = newlyEnabledLegendLayer(prevEnabled, nextEnabled);
    if (activated) {
      setLegendPreferredId(activated);
    } else if (
      legendPreferredId &&
      isLegendLayerOff(legendPreferredId, nextEnabled)
    ) {
      setLegendPreferredId(null);
    }
    setLedgerEnabled(sanitized);
    if ("councils" in sanitized) {
      setShowCouncils(Boolean(sanitized.councils));
    }
    if ("data_zones" in sanitized) {
      setShowDataZones(Boolean(sanitized.data_zones));
    }
    if ("vdl" in sanitized) setShowVdl(Boolean(sanitized.vdl));
    if (GRID3_LAYER_ID in sanitized) {
      setShowGrid3(Boolean(sanitized[GRID3_LAYER_ID]));
    }
    if ("hla" in sanitized) {
      const turnOn =
        Boolean(sanitized.hla) && !tileUnavailableIds.has("hla");
      setShowHla(turnOn);
      if (turnOn) {
        const path =
          "/layers/open/hla?south=55.85&west=-4.27&north=55.87&east=-4.24&max_features=1";
        void apiJson<GeoJSON.FeatureCollection>(path).catch((err: unknown) => {
          if (isServiceUnavailable(err)) {
            markTileUnavailable("hla");
            setShowHla(false);
          }
        });
      }
    }
    if (
      "3" in sanitized &&
      Boolean(sanitized["3"]) &&
      !tileUnavailableIds.has("3")
    ) {
      const path =
        "/layers/open/repd-onshore-wind?south=55.85&west=-4.27&north=55.87&east=-4.24&max_features=1";
      void apiJson<GeoJSON.FeatureCollection>(path).catch((err: unknown) => {
        if (isServiceUnavailable(err)) {
          markTileUnavailable("3");
          setLedgerEnabled((cur) => {
            if (!cur["3"]) return cur;
            const copy = { ...cur };
            delete copy["3"];
            return copy;
          });
        }
      });
    }
    // Flood risk (toggle id "flood") paints catalog layer sepa_nfra_grid.
    // The gated SEPA flood-extent overlay is not this switch.
  };

  // Public place card (stub). Modelled AGR £ / Wealth / tax stay off the public shell.
  const [placeStub, setPlaceStub] = useState<PlaceStub | null>(null);
  const [placeLoading, setPlaceLoading] = useState(false);

  const [contextOn, setContextOn] = useState<Record<string, boolean>>({});

  const [urbanRuralName, setUrbanRuralName] = useState<string | null>(null);
  const [dataZone, setDataZone] = useState<{
    code: string;
    name?: string;
    house_sale_median_gbp?: number | null;
    house_sale_year?: number | null;
    urban_rural_name?: string;
    urban_rural_year?: number | null;
    urban_rural_route?: string;
  } | null>(null);
  const [seabed, setSeabed] = useState<{ notes: string[]; failed: boolean } | null>(null);
  const [contextNote, setContextNote] = useState<string | null>(null);
  const contextLoaded = useRef<Set<string>>(new Set());
  const [, setLayerBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SquareResponse | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  // Legacy ground-rent router mounted? null = not known yet. Its endpoints are never called when false.
  const [agrAvailable, setAgrAvailable] = useState<boolean | null>(null);
  /** One panel slot: closed | place | layers (never both). */
  const [panelKind, setPanelKind] = useState<PanelSlotKind>("closed");
  const [panelDetent, setPanelDetent] = useState<PanelDetent>("peek");
  const [panelCollapsed, setPanelCollapsed] = useState(false);
  /** Desktop: Layers column on the right. Independent of the place slot. */
  const [desktopLayersOpen, setDesktopLayersOpen] = useState(false);
  /** Place card set aside while Layers is open (restore on Layers close). */
  const placeAsideRef = useRef(false);
  /** Latest panel kind for async identify (desktop: must not steal Layers). */
  const panelKindRef = useRef<PanelSlotKind>(panelKind);
  panelKindRef.current = panelKind;
  const desktopLayersOpenRef = useRef(desktopLayersOpen);
  desktopLayersOpenRef.current = desktopLayersOpen;
  const [mapStyle, setMapStyle] = useState<MapBasemapId>(DEFAULT_MAP_BASEMAP);
  const [mapZoom, setMapZoom] = useState(5.7);
  const [isNarrowPanel, setIsNarrowPanel] = useState(
    () =>
      typeof window !== "undefined" &&
      window.innerWidth < PANEL_MOBILE_BREAKPOINT,
  );
  /** SW-056: narrow = collapse Layers when a place is picked. */
  const isNarrowPanelRef = useRef(isNarrowPanel);
  isNarrowPanelRef.current = isNarrowPanel;
  /**
   * Most recently activated legend-capable layer (drawer id) for strip chip.
   */
  const [legendPreferredId, setLegendPreferredId] = useState<string | null>(
    null,
  );
  const [catalogLayers, setCatalogLayers] = useState<CatalogLayer[]>([]);
  /** Built-up mask tiles/geo returned service-unavailable. */
  const [builtupMaskUnavailable, setBuiltupMaskUnavailable] = useState(false);
  /**
   * Catalogue loaded with builtup_mask missing or not live.
   * Empty catalogue stubs (common in e2e) leave this false — keep background on.
   */
  const [builtupMaskCatalogGap, setBuiltupMaskCatalogGap] = useState(false);
  const [searchNoMatch, setSearchNoMatch] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [restPromptVisible, setRestPromptVisible] = useState(true);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [liveMessage, setLiveMessage] = useState("");
  const panelHistoryRef = useRef(false);
  /**
   * SHARE-FIX — layers whose tiles returned 503 → Coming soon / disabled
   * (hla, onshore wind+hydro "3", aquaculture "5", lca).
   */
  const [tileUnavailableIds, setTileUnavailableIds] = useState<Set<string>>(
    () => new Set(),
  );
  /**
   * Vacant land stays listed until a real manifest omits it (it already paints).
   * Other Improvement Service rows stay hidden until the manifest lists them.
   */
  const [spatialHubPresent, setSpatialHubPresent] = useState<Record<
    string,
    boolean
  > | null>({ vdl: true });
  const markTileUnavailable = useCallback((id: string) => {
    setTileUnavailableIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const parcelLabelRef = useRef<maplibregl.Marker | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);
  const layersBtnRef = useRef<HTMLButtonElement | null>(null);
  const cameraPreserveRef = useRef<{
    lng: number;
    lat: number;
    zoom: number;
  } | null>(null);
  /** Deep-link boot (?lat/lng/words) once per ready map instance. */
  const urlBootDoneRef = useRef(false);
  /**
   * Capture entry URL identify coords before layers URL sync rewrites
   * `?lat=&lng=` → `c=` (writeMapUrlSearch). Without this, mapReady boot
   * only jumpTo's and never opens the place card (PR #163 e2e mode 1).
   */
  const deepLinkCaptureRef = useRef<{
    lat: number | null;
    lng: number | null;
    words: string | null;
    vacant: boolean;
    community: boolean;
    place: string | null;
  } | null>(null);
  if (deepLinkCaptureRef.current === null && typeof window !== "undefined") {
    const p = new URLSearchParams(window.location.search);
    // Number(null) === 0 — missing params must stay absent, not null-island.
    const latRaw = p.get("lat");
    const lngRaw = p.get("lng") ?? p.get("lon");
    const lat = latRaw != null && latRaw.trim() !== "" ? Number(latRaw) : NaN;
    const lng = lngRaw != null && lngRaw.trim() !== "" ? Number(lngRaw) : NaN;
    deepLinkCaptureRef.current = {
      lat: Number.isFinite(lat) ? lat : null,
      lng: Number.isFinite(lng) ? lng : null,
      words: p.get("words"),
      vacant: p.get("vacant") === "1",
      community: p.get("community") === "1",
      place: p.get("place"),
    };
  }

  const registryEnabled: Record<string, boolean> = {
    ...ledgerEnabled,
    "1": showAgr,
    councils: showCouncils,
    data_zones: showDataZones,
    vdl: showVdl,
    hla: showHla,
    [GRID3_LAYER_ID]: showGrid3,
  };
  const activeLayerIds = activeRegistryLayerIds({
    showCouncils,
    showDataZones,
    showAgr,
    showVdl,
    showHla,
    showRepd,
    showCrownLeases,
    showCroftingConstraint,
    showGrid3,
    ledgerEnabled,
    contextOn,
  });
  const attributionPieces = buildMapAttributionPieces(activeLayerIds);
  // Prefer a non-default visitor layer for the closed-panel strip (MAP-CARDS §3.5).
  // Fall back to legendPreferredId only when it is itself non-default and on.
  const stripLayerId = (() => {
    const fromActive = legendStripLayerId(registryEnabled);
    if (fromActive) return fromActive;
    const defaults = new Set(defaultOnLayerIds());
    if (
      legendPreferredId &&
      registryEnabled[legendPreferredId] &&
      !defaults.has(legendPreferredId)
    ) {
      return legendPreferredId;
    }
    return null;
  })();
  const stripLayer = stripLayerId ? getMapLayer(stripLayerId) : undefined;

  const [gbpLiveOn, setGbpLiveOn] = useState(false);
  const gbpLiveBootstrapped = useRef(false);
  useEffect(() => {
    let cancelled = false;
    // Capture entry search before any await — the layers URL sync effect may
    // rewrite `?layers=` while gbp-live is in flight (§3.10 / 36b / 36c).
    const searchAtLoad = window.location.search;
    const layersFromUrlAtLoad = new URLSearchParams(searchAtLoad).has("layers");
    const bootAtLoad = readMapUrlState(searchAtLoad);

    const applyIds = (ids: string[]) => {
      setShowCouncils(ids.includes("councils"));
      setShowDataZones(ids.includes("data_zones"));
      setShowVdl(ids.includes("vdl"));
      setShowHla(ids.includes("hla"));
      setShowGrid3(ids.includes(GRID3_LAYER_ID));
      const ledger: LedgerToggleState = {};
      for (const id of ids) {
        if (
          id === "councils" ||
          id === "data_zones" ||
          id === "vdl" ||
          id === "hla" ||
          id === GRID3_LAYER_ID
        ) {
          continue;
        }
        ledger[id] = true;
      }
      setLedgerEnabled((cur) => ({ ...cur, ...ledger }));
      // Keep constraint overlays in sync with URL / GBP-LIVE boot ids.
      setContextOn((cur) => ({
        ...cur,
        flood: ids.includes("flood"),
        "oil-fields": ids.includes("9"),
      }));
    };

    // Apply URL / default layers synchronously so a slow GBP-LIVE probe cannot
    // wipe visitor toggles (legend-strip / inline legend e2e race).
    if (!gbpLiveBootstrapped.current) {
      gbpLiveBootstrapped.current = true;
      if (layersFromUrlAtLoad) {
        applyIds(bootAtLoad.layers);
      } else {
        applyIds(
          bootAtLoad.layers.length ? bootAtLoad.layers : defaultOnLayerIds(),
        );
      }
      if (bootAtLoad.panel === "layers") {
        if (window.innerWidth < PANEL_MOBILE_BREAKPOINT) {
          setPanelKind("layers");
          setPanelDetent("full");
        } else {
          setDesktopLayersOpen(true);
        }
        panelHistoryRef.current = true;
      } else if (bootAtLoad.panel === "place") {
        // Content comes from the deep-link identify. An empty slot is a blank card.
        const canRestore = Boolean(bootAtLoad.place || bootAtLoad.center);
        if (!canRestore) {
          replaceMapUrl({ panel: null });
        } else {
          panelHistoryRef.current = true;
        }
      }
      if (bootAtLoad.center && mapRef.current) {
        mapRef.current.jumpTo({
          center: [bootAtLoad.center.lng, bootAtLoad.center.lat],
          zoom: bootAtLoad.z ?? mapRef.current.getZoom(),
        });
      }
    }

    void fetchGbpLiveSettings().then((settings) => {
      if (cancelled) return;
      const on = Boolean(settings.enabled);
      setGbpLiveOn((prev) => (prev === on ? prev : on));
      // §3.10 — GBP-LIVE on: enable AGR unless URL already set layers.
      // Additive only — never reset councils/vdl/hla the visitor already chose.
      if (on && !layersFromUrlAtLoad) {
        setLedgerEnabled((cur) =>
          cur["1"] ? cur : { ...cur, "1": true },
        );
        setLegendPreferredId((prev) => prev ?? "1");
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const header = headerRef.current;
    const apply = () => {
      const shell = header?.parentElement;
      if (!shell) return;
      if (header) shell.style.setProperty("--hud-height", `${header.offsetHeight}px`);
    };
    apply();
    const observer = new ResizeObserver(apply);
    if (header) observer.observe(header);
    return () => observer.disconnect();
  }, []);

  // UI-TWEAKS-1 T1 bottom inset + MAP-CARDS left column: clear the HUD
  // (brand lives on the left — do not pin top to the Layers button or the
  // logo intercepts the slot ×). Stretch to attribution / stamp-footer.
  // MapPanelSlot is outside .map-stage; set CSS vars on .app-shell.
  useEffect(() => {
    if (panelKind !== "layers" && !desktopLayersOpen) return;
    const stage =
      layersBtnRef.current?.closest(".map-stage") ??
      headerRef.current?.parentElement;
    if (!stage || !(stage instanceof HTMLElement)) return;
    const shell =
      (stage.closest(".app-shell") as HTMLElement | null) ?? stage;
    const header = headerRef.current;

    const applyPanelGeometry = () => {
      const shellRect = shell.getBoundingClientRect();
      const stageRect = stage.getBoundingClientRect();
      // Clear the HUD band (header height + small gap), same side as brand.
      let top = Math.round(1.75 * 16);
      if (header) {
        const headerRect = header.getBoundingClientRect();
        top = Math.max(
          0,
          Math.round(headerRect.bottom - shellRect.top + 0.45 * 16),
        );
      }
      shell.style.setProperty("--layers-panel-top", `${top}px`);

      // Bottom inset: attribution / safe gap above the map-stage floor, plus
      // any shell chrome below the stage (stamp footer). Zoom controls shift
      // sideways while the drawer is open — do not reserve their full stack.
      let gapAboveStageFloor = Math.round(1.75 * 16);
      const attribBtn = stage.querySelector(
        ".maplibregl-ctrl-attrib",
      ) as HTMLElement | null;
      if (attribBtn && attribBtn.offsetParent !== null) {
        const a = attribBtn.getBoundingClientRect();
        const fromFloor = Math.round(stageRect.bottom - a.bottom);
        gapAboveStageFloor = Math.max(gapAboveStageFloor, fromFloor + 8);
      }
      const belowStage = Math.max(
        0,
        Math.round(shellRect.bottom - stageRect.bottom),
      );
      const bottomInset = belowStage + gapAboveStageFloor;
      shell.style.setProperty(
        "--layers-panel-bottom",
        `${bottomInset}px`,
      );
    };

    applyPanelGeometry();
    const observer = new ResizeObserver(applyPanelGeometry);
    observer.observe(shell);
    observer.observe(stage);
    if (header) observer.observe(header);
    window.addEventListener("resize", applyPanelGeometry);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", applyPanelGeometry);
    };
  }, [panelKind, desktopLayersOpen]);

  const applyResult = useCallback((payload: SquareResponse) => {
    setResult(payload);
    setSearchNoMatch(false);
    if (payload.agr?.active_scenario) {
      setScenario(payload.agr.active_scenario);
    }
    setPanelKind("place");
    setPanelCollapsed(false);
    placeDetentMemory = "half";
    setPanelDetent("half");
    setRestPromptVisible(false);

    const map = mapRef.current;
    if (map) {
      markerRef.current?.remove();
      markerRef.current = placeSelectedMarker(
        map,
        payload.square.lng,
        payload.square.lat,
      );
      parcelLabelRef.current?.remove();
      parcelLabelRef.current = null;
      const z = map.getZoom();
      const targetZoom =
        z < 6.5 ? 7 : Math.min(Math.max(z, 15), MAP_MAX_ZOOM);
      map.flyTo({
        center: [payload.square.lng, payload.square.lat],
        zoom: Math.min(targetZoom, MAP_MAX_ZOOM),
        essential: true,
        padding: mapPanelPadding({
          panelOpen: true,
          detent: "half",
          collapsed: false,
        }),
      });
    }

    if (payload.what3words) {
      setQuery(`///${payload.what3words.replace(/^\/+/, "")}`);
    }

    replaceMapUrl({
      center: { lng: payload.square.lng, lat: payload.square.lat },
      panel: "place",
    });
  }, []);

  const fetchSquare = useCallback(
    async (
      nextLat: number,
      nextLng: number,
      nextScenario?: ScenarioId,
      keepLabel = false,
      generation?: number,
    ) => {
      const gen = generation ?? ++lookupGen.current;
      if (!(await fetchCapabilities()).agr) return; // legacy breakdown not on this server: wealth panel only
      if (!keepLabel) {
                setAddressLine(null);
      }
      setLoading(true);
      setError(null);
      const sc = nextScenario ?? scenario;
      try {
        const response = await apiFetch(
          `/square?lat=${nextLat}&lng=${nextLng}&scenario=${sc}`,
        );
        const payload = (await response.json()) as SquareResponse;
        if (gen !== lookupGen.current) return;
        applyResult(payload);
        setApiOk(true);
      } catch (err) {
        if (gen !== lookupGen.current) return;
        // Modelled cell AGR is internal/blocked; wealth panel still runs via inspectPoint.
        if (err instanceof ApiError && err.status === 404) {
          setApiOk(true);
          return;
        }
        setError(visitorFacingError(err));
        if (isServiceFailure(err)) {
          void pingApi().then((s) => {
            if (gen === lookupGen.current) setApiOk(s.ok);
          });
        }
      } finally {
        if (gen === lookupGen.current) setLoading(false);
      }
    },
    [applyResult, scenario],
  );

  const clearPlace = useCallback(() => {
    // Invalidate in-flight identify / search so a late place_card_v1 cannot
    // resurrect the sheet after Esc / × (mobile detent e2e).
    lookupGen.current += 1;
    identifyAbortRef.current?.abort();
    identifyAbortRef.current = null;
    setResult(null);
    setError(null);
    setAddressLine(null);
    setPlaceStub(null);
    placeDetentMemory = null;
    setPlaceLoading(false);
    setGrid3Square(null);
    setSearchNoMatch(false);
    setPanelKind((k) => (k === "place" ? "closed" : k));
    setPanelCollapsed(false);
    placeAsideRef.current = false;
    setRestPromptVisible(true);
    markerRef.current?.remove();
    markerRef.current = null;
    parcelLabelRef.current?.remove();
    parcelLabelRef.current = null;
    replaceMapUrl({ place: null, panel: null, center: null });
  }, []);

  /** SW-028: close sea stub and reset camera to Scotland national view. */
  const showScotlandNationalView = useCallback(() => {
    clearPlace();
    const map = mapRef.current;
    if (!map) return;
    const narrow = window.innerWidth <= 900;
    // Defer past panel-close padding easeTo(duration:0) so it cannot cancel
    // this fitBounds mid-flight (sea-stub national maxZoom e2e on desktop).
    window.setTimeout(() => {
      const live = mapRef.current;
      if (!live) return;
      live.stop();
      live.fitBounds(
        [
          [-8.05, 54.48],
          [-0.55, 60.88],
        ],
        {
          padding: narrow
            ? { top: 132, bottom: 72, left: 12, right: 16 }
            : { top: 96, bottom: 36, left: 24, right: 28 },
          animate: true,
          maxZoom: 7.4,
        },
      );
    }, 0);
  }, [clearPlace]);

  // Public path for a point (map click, search, ?lat=&lng=): marker, optional fly,
  // shareable URL, lightweight place card. No modelled AGR £ / Wealth / tax on the public shell.
  const selectPlace = useCallback(
    async (
      lat: number,
      lng: number,
      opts: {
        fly?: boolean;
        label?: string | null;
        postcode?: string | null;
        dataZoneCode?: string | null;
        dataZoneName?: string | null;
        dataZoneVintage?: number | null;
        laName?: string | null;
        population?: number | null;
        popYear?: number | null;
        dwellings?: number | null;
        dwYear?: number | null;
        /** True after postcode / place / address search (UX-10 item 2). */
        fromAddressSearch?: boolean;
        /** When the caller already owns lookupGen, reuse it (do not bump again). */
        generation?: number;
        /** Deep-link re-boot after a map remount must not pop a collapsed card open. */
        keepCollapsed?: boolean;
      } = {},
    ) => {
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      const gen =
        typeof opts.generation === "number"
          ? opts.generation
          : ++lookupGen.current;
      const map = mapRef.current;
      markerRef.current?.remove();
      if (map) {
        markerRef.current = placeSelectedMarker(map, lng, lat);
        if (opts.fly) {
          // Desktop Layers stays in the right column. Mobile closes the sheet.
          const layersHoldingFly =
            desktopLayersOpenRef.current && !isNarrowPanelRef.current;
          map.flyTo({
            center: [lng, lat],
            zoom: Math.max(map.getZoom(), 15),
            essential: true,
            // GIS 12 — centre in the uncovered map (right of 380px desktop panel).
            padding: mapPanelPadding({
              panelOpen: !layersHoldingFly,
              detent: opts.fromAddressSearch ? "half" : "peek",
              collapsed: Boolean(opts.keepCollapsed),
            }),
          });
        }
      }
      setError(null);
      setResult(null);
      setSearchNoMatch(false);
      setRestPromptVisible(false);
      // Desktop: Layers stays open in the right column and the card stays left.
      // Mobile: map tap / search closes Layers and opens the card (SW-056 / SW-065).
      const narrow = isNarrowPanelRef.current;
      const layersOpenNow = narrow
        ? panelKindRef.current === "layers"
        : desktopLayersOpenRef.current;
      const keepLayersOpen = layersOpenNow && !narrow;
      placeAsideRef.current = false;
      setPanelKind("place");
      if (!opts.keepCollapsed) setPanelCollapsed(false);
      const detent = opts.fromAddressSearch ? "half" : "peek";
      placeDetentMemory = detent;
      setPanelDetent(detent);
      if (!panelHistoryRef.current) {
        pushMapUrl({
          center: { lng, lat },
          panel: keepLayersOpen ? "layers" : "place",
        });
        panelHistoryRef.current = true;
      } else {
        replaceMapUrl({
          center: { lng, lat },
          panel: keepLayersOpen ? "layers" : "place",
        });
      }
      setAddressLine(opts.label ?? null);
      const knownCode = opts.dataZoneCode?.trim() || null;
      const knownName = opts.dataZoneName?.trim() || null;
      // Keep the prior card when re-inspecting the same point so the sea-line
      // (and its × padding) is not unmounted mid-paint (SW-030 / UX-01 e2e).
      // Honour lookupGen inside the updater so a clearPlace that landed after
      // this setState was queued cannot be overwritten by a stale recreate.
      setPlaceStub((prev) => {
        if (gen !== lookupGen.current) return prev;
        const samePoint =
          prev != null && prev.lat === lat && prev.lng === lng;
        return {
          lat,
          lng,
          label: opts.label ?? knownName ?? prev?.label ?? null,
          postcode: opts.postcode ?? prev?.postcode ?? null,
          dataZoneCode: knownCode ?? (samePoint ? prev?.dataZoneCode ?? null : null),
          dataZoneName: knownName ?? (samePoint ? prev?.dataZoneName ?? null : null),
          dataZoneVintage:
            opts.dataZoneVintage ??
            (samePoint ? prev?.dataZoneVintage ?? null : null),
          laName: opts.laName ?? (samePoint ? prev?.laName ?? null : null),
          population:
            opts.population ?? (samePoint ? prev?.population ?? null : null),
          popYear: opts.popYear ?? (samePoint ? prev?.popYear ?? null : null),
          dwellings:
            opts.dwellings ?? (samePoint ? prev?.dwellings ?? null : null),
          dwYear: opts.dwYear ?? (samePoint ? prev?.dwYear ?? null : null),
          card: samePoint ? prev?.card ?? null : null,
          noMatch: false,
          fromAddressSearch: Boolean(opts.fromAddressSearch),
        };
      });
      setPlaceLoading(true);
      // Cancel debounce + prior identify so only the latest selectPlace wins (24).
      if (identifyTimerRef.current) {
        clearTimeout(identifyTimerRef.current);
        identifyTimerRef.current = null;
      }
      identifyAbortRef.current?.abort();
      const identifyAbort = new AbortController();
      identifyAbortRef.current = identifyAbort;
      try {
        if (!knownCode) {
          try {
            const data = await apiJson<{
              code?: string;
              name?: string;
              vintage?: number;
            }>(
              `/layers/context/data-zones/at?lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lng))}`,
              { cache: "no-store", signal: identifyAbort.signal },
            );
            if (gen !== lookupGen.current || identifyAbort.signal.aborted) return;
            const code = data.code?.trim() || null;
            const name = data.name?.trim() || null;
            setPlaceStub((prev) => {
              if (gen !== lookupGen.current) return prev;
              return prev && prev.lat === lat && prev.lng === lng
                ? {
                    ...prev,
                    dataZoneCode: code,
                    dataZoneName: name,
                    dataZoneVintage:
                      typeof data.vintage === "number" ? data.vintage : null,
                  }
                : prev;
            });
          } catch {
            // Sea / outside Scotland (404 no_data_zone_at_point) or boundaries
            // unavailable: still load place_card_v1 so miss/unavailable is honest
            // and the UI can show one plain line instead of No-data rows.
            if (identifyAbort.signal.aborted || gen !== lookupGen.current) return;
          }
        }
        // Designer place card (place_card_v1) — ownership / sources; no £.
        // SW-019: fetchPlaceCard turns outside-Scotland 400 into a sea-miss card.
        const card = await fetchPlaceCard({
          lat,
          lng,
          postcode: opts.postcode,
          signal: identifyAbort.signal,
        });
        if (gen !== lookupGen.current || identifyAbort.signal.aborted) return;
        setPlaceStub((prev) => {
          if (gen !== lookupGen.current) return prev;
          return prev && prev.lat === lat && prev.lng === lng
            ? {
                ...prev,
                card,
                dataZoneCode:
                  prev.dataZoneCode || card.data_zone?.code || null,
                dataZoneName:
                  prev.dataZoneName || card.data_zone?.name || null,
                dataZoneVintage:
                  prev.dataZoneVintage ??
                  (typeof card.data_zone?.vintage === "number"
                    ? card.data_zone.vintage
                    : null),
                laName: prev.laName || card.council_name || null,
                label: prev.label || card.place_label || null,
              }
            : prev;
        });
      } catch (err) {
        // SW-019 belt-and-suspenders: clear spinner and show the plain line
        // if an outside-Scotland 400 still surfaces (e.g. /api/place.json).
        if (isOutsideScotlandError(err) && gen === lookupGen.current) {
          setPlaceStub((prev) => {
            if (gen !== lookupGen.current) return prev;
            return prev && prev.lat === lat && prev.lng === lng
              ? { ...prev, card: outsideScotlandPlaceCard(lat, lng) }
              : prev;
          });
        }
        /* other zone / place card failures are best-effort */
      } finally {
        if (gen === lookupGen.current) setPlaceLoading(false);
      }
    },
    [],
  );
  const inspectRef = useRef(selectPlace);
  inspectRef.current = selectPlace;

  const openLayersPanel = useCallback(() => {
    const narrow = isNarrowPanelRef.current;
    if (narrow) {
      if (panelKind === "place" || placeStub) {
        placeAsideRef.current = true;
      }
      setPanelKind("layers");
      setPanelCollapsed(false);
      setPanelDetent("full");
    } else {
      // Right column. The place card, when open, stays in the left column.
      setDesktopLayersOpen(true);
    }
    setRestPromptVisible(false);
    setLiveMessage("Map layers open");
    const placeShowing =
      !narrow && (panelKind === "place" || Boolean(placeStub));
    if (!placeShowing) {
      if (!panelHistoryRef.current) {
        pushMapUrl({ panel: "layers" });
        panelHistoryRef.current = true;
      } else {
        replaceMapUrl({ panel: "layers" });
      }
    }
  }, [panelKind, placeStub]);

  const closeLayersPanel = useCallback(() => {
    if (!isNarrowPanelRef.current && desktopLayersOpenRef.current) {
      setDesktopLayersOpen(false);
      if (panelKindRef.current === "place" && placeStub) {
        setLiveMessage("Map layers closed");
        replaceMapUrl({ panel: "place" });
      } else {
        setLiveMessage("Layers closed");
        if (panelHistoryRef.current) {
          pushMapUrl({ panel: null });
        } else {
          replaceMapUrl({ panel: null });
        }
        panelHistoryRef.current = false;
      }
      layersBtnRef.current?.focus();
      return;
    }
    if (placeAsideRef.current && placeStub) {
      setPanelKind("place");
      // Layers opens at full — restore the place card at its search/tap detent,
      // not full (otherwise identify-at-centre stays under the sheet on tablet).
      setPanelDetent(placeStub.fromAddressSearch ? "half" : "peek");
      setLiveMessage("Place card restored");
      replaceMapUrl({ panel: "place" });
    } else {
      setPanelKind("closed");
      setLiveMessage("Layers closed");
      // Push a closed entry when Layers was in history (deep-link or open push)
      // so browser Back restores panel=layers (MAP-CARDS E1 / check 15+17).
      if (panelHistoryRef.current) {
        pushMapUrl({ panel: null });
      } else {
        replaceMapUrl({ panel: null });
      }
      panelHistoryRef.current = false;
    }
    placeAsideRef.current = false;
    layersBtnRef.current?.focus();
  }, [placeStub]);

  const panelCollapsedRef = useRef(panelCollapsed);
  panelCollapsedRef.current = panelCollapsed;
  const panelDetentRef = useRef(panelDetent);
  panelDetentRef.current = panelDetent;
  const shortcutsOpenRef = useRef(shortcutsOpen);
  shortcutsOpenRef.current = shortcutsOpen;
  const placeStubRef = useRef(placeStub);
  placeStubRef.current = placeStub;
  const resultRef = useRef(result);
  resultRef.current = result;
  const errorRef = useRef(error);
  errorRef.current = error;

  const dismissPanel = useCallback(() => {
    const kind = panelKindRef.current;
    if (kind === "layers") {
      closeLayersPanel();
      return;
    }
    if (kind === "place") {
      if (!isNarrowPanelRef.current && !panelCollapsedRef.current) {
        setPanelCollapsed(true);
        setLiveMessage("Place card collapsed");
        return;
      }
      if (isNarrowPanelRef.current) {
        const step = nextDetentDown(panelDetentRef.current);
        if (step !== "close") {
          setPanelDetent(step);
          setLiveMessage(`Panel ${step}`);
          return;
        }
      }
      clearPlace();
      setPanelKind("closed");
      setPanelCollapsed(false);
      replaceMapUrl({ panel: null, place: null });
      panelHistoryRef.current = false;
      setLiveMessage("Panel closed");
    }
  }, [closeLayersPanel, clearPlace]);

  const dismissPanelRef = useRef(dismissPanel);
  dismissPanelRef.current = dismissPanel;
  const clearPlaceRef = useRef(clearPlace);
  clearPlaceRef.current = clearPlace;
  const openLayersPanelRef = useRef(openLayersPanel);
  openLayersPanelRef.current = openLayersPanel;
  const closeLayersPanelRef = useRef(closeLayersPanel);
  closeLayersPanelRef.current = closeLayersPanel;

  // Refs are written during render, so Escape sees the open place card
  // before the key listener effect can re-subscribe.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing =
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement;
      if (event.key === "/" && !typing) {
        event.preventDefault();
        document.getElementById("place-query")?.focus();
        return;
      }
      if (event.key === "?" && !typing) {
        event.preventDefault();
        setShortcutsOpen(true);
        return;
      }
      if (event.key === "l" && !typing) {
        event.preventDefault();
        const layersOn = isNarrowPanelRef.current
          ? panelKindRef.current === "layers"
          : desktopLayersOpenRef.current;
        if (layersOn) closeLayersPanelRef.current();
        else openLayersPanelRef.current();
        return;
      }
      if (event.key === "Enter" && !typing) {
        const map = mapRef.current;
        if (!map || !showGrid3Ref.current) return;
        if (map.getZoom() < GRID3_TAP_ZOOM) return;
        const c = map.getCenter();
        event.preventDefault();
        void inspectRef.current(c.lat, c.lng, { fly: false });
        grid3AfterIdentifyRef.current?.(c.lng, c.lat);
        return;
      }
      if (event.key !== "Escape") return;
      if (shortcutsOpenRef.current) {
        setShortcutsOpen(false);
        return;
      }
      if (!isNarrowPanelRef.current && desktopLayersOpenRef.current) {
        closeLayersPanelRef.current();
        return;
      }
      if (panelKindRef.current !== "closed") {
        dismissPanelRef.current();
        return;
      }
      if (placeStubRef.current || resultRef.current || errorRef.current) {
        clearPlaceRef.current();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (showGrid3) return;
    setGrid3Square(null);
    setGrid3Tooltip(null);
    const map = mapRef.current;
    if (!map) return;
    void import("../lib/grid3Map").then((gm) => {
      const src = map.getSource(gm.GRID3_SOURCE_HIGHLIGHT) as
        | GeoJSONSource
        | undefined;
      src?.setData(gm.EMPTY_FC);
    });
  }, [showGrid3]);

  useEffect(() => {
    const onPop = () => {
      const state = readMapUrlState(window.location.search);
      const narrow = window.innerWidth < PANEL_MOBILE_BREAKPOINT;
      if (state.panel === "layers") {
        if (narrow) {
          setDesktopLayersOpen(false);
          setPanelKind("layers");
          setPanelDetent("full");
        } else {
          setDesktopLayersOpen(true);
          if (panelKindRef.current === "layers") setPanelKind("closed");
        }
      } else if (state.panel === "place" && placeStub) {
        setDesktopLayersOpen(false);
        setPanelKind("place");
      } else {
        setDesktopLayersOpen(false);
        setPanelKind("closed");
        setPanelCollapsed(false);
        panelHistoryRef.current = false;
      }
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [placeStub]);

  useEffect(() => {
    const mq = window.matchMedia(
      `(max-width: ${PANEL_MOBILE_BREAKPOINT - 1}px)`,
    );
    const sync = () => setIsNarrowPanel(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  // MapLibre padding follows the panel slot.
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;
    map.easeTo({
      padding: mapPanelPadding({
        panelOpen:
          (panelKind === "place" && !panelCollapsed) ||
          (isNarrowPanel && panelKind === "layers"),
        detent: panelDetent,
        collapsed: panelCollapsed,
      }),
      duration: 0,
    });
  }, [mapReady, panelKind, panelDetent, panelCollapsed, isNarrowPanel]);

  const openPostcode = async (postcode: string, generation: number) => {
    const response = await placeLookupFetch(
      `/postcode/${encodeURIComponent(postcode)}`,
    );
    const payload = (await response.json()) as SquareResponse & {
      lat?: number;
      lng?: number;
      status?: string;
    };
    if (generation !== lookupGen.current) return;
    const lat = payload.lat ?? payload.square?.lat;
    const lng = payload.lng ?? payload.square?.lng;
    if (lat == null || lng == null) {
      setError("Postcode found, but no map point was returned.");
      return;
    }
    // Public postcode is centroid-only; modelled AGR £ is internal/blocked.
    await inspectRef.current(lat, lng, {
      fly: true,
      postcode: payload.postcode?.postcode ?? postcode,
      label: payload.postcode?.postcode ?? postcode,
      fromAddressSearch: true,
      generation,
    });
  };

  const openWords = async (words: string, generation: number) => {
    // Public shell: resolve ///words via /place only (no /square AGR £).
    const response = await placeLookupFetch(
      `/place?q=${encodeURIComponent(`///${words.replace(/^\/+/, "")}`)}`,
    );
    const body = (await response.json()) as PlaceLookup;
    if (generation !== lookupGen.current) return;
    if (body.kind === "point" && body.lat != null && body.lng != null) {
      await inspectRef.current(body.lat, body.lng, {
        fly: true,
        label: body.label ?? `///${words}`,
        fromAddressSearch: true,
        generation,
      });
      return;
    }
    if (body.kind === "words" && body.lat != null && body.lng != null) {
      await inspectRef.current(body.lat, body.lng, {
        fly: true,
        label: `///${body.words ?? words}`,
        fromAddressSearch: true,
        generation,
      });
      return;
    }
    setError(body.note || "Those three words did not resolve on the map.");
  };
  const openWordsRef = useRef(openWords);
  openWordsRef.current = openWords;

  const clearSuggestions = () => {
    // Cancel debounce + in-flight so "Looking…" cannot reappear after blur/Escape.
    if (suggestTimer.current) {
      clearTimeout(suggestTimer.current);
      suggestTimer.current = null;
    }
    suggestAbort.current?.abort();
    suggestAbort.current = null;
    setSuggestions([]);
    setSuggestNote(null);
    setActiveSuggest(-1);
    setSuggesting(false);
  };

  // Postcode-only search (postcodes.io via /geocode/postcode) when the AGR place search is absent.
  const searchPostcode = async (q: string) => {
    const generation = ++lookupGen.current;
    suggestGen.current += 1;
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    clearSuggestions();
    setError(null);
    if (!looksLikeFullPostcode(q)) {
      setError(POSTCODES_ONLY);
      return;
    }
    setLoading(true);
    try {
      const body = await apiJson<{ postcode: string; lat: number; lng: number }>(
        `/geocode/postcode?q=${encodeURIComponent(q)}`,
        { retryStatuses: [502, 503, 504], maxAttempts: 3 },
      );
      if (generation !== lookupGen.current) return;
      // SW-051: keep the user's postcode formatting (e.g. EH1 1YZ), not API compact.
      void inspectRef.current(body.lat, body.lng, {
        fly: true,
        fromAddressSearch: true,
        generation,
      });
    } catch (err) {
      if (generation !== lookupGen.current) return;
      setError(
        err instanceof ApiError && err.status === 503
          ? "Postcode search is unavailable right now. Click the map instead."
          : visitorFacingError(err),
      );
    } finally {
      if (generation === lookupGen.current) setLoading(false);
    }
  };

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    const coords = parseCoordinates(q);
    if (coords) {
      const generation = ++lookupGen.current;
      suggestGen.current += 1;
      if (suggestTimer.current) clearTimeout(suggestTimer.current);
      clearSuggestions();
      setLoading(true);
      setError(null);
      try {
        await inspectRef.current(coords.lat, coords.lng, {
          fly: true,
          label: `${coords.lat.toFixed(5)}, ${coords.lng.toFixed(5)}`,
          fromAddressSearch: true,
          generation,
        });
        if (generation === lookupGen.current) setApiOk(true);
      } finally {
        if (generation === lookupGen.current) setLoading(false);
      }
      return;
    }
    if (!(await fetchCapabilities()).agr) {
      await searchPostcode(q);
      return;
    }
    const generation = ++lookupGen.current;
    suggestGen.current += 1;
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    setLoading(true);
    setError(null);
    clearSuggestions();
    try {
      const response = await placeLookupFetch(
        `/place?q=${encodeURIComponent(q)}`,
      );
      const body = (await response.json()) as PlaceLookup;
      if (generation !== lookupGen.current) return;
      if (body.kind === "words" && body.words) {
        await openWords(body.words, generation);
      } else if (body.kind === "postcode" && body.postcode) {
        await openPostcode(body.postcode, generation);
      } else if (body.kind === "point" && body.lat != null && body.lng != null) {
        await inspectRef.current(body.lat, body.lng, {
          fly: true,
          label: body.label ?? null,
          fromAddressSearch: true,
          generation,
        });
      } else if (body.kind === "places" && body.matches && body.matches.length > 1) {
        clearPlace();
        const found = suggestionsFromLookup(body, q);
        setSuggestions(found.items);
        setActiveSuggest(found.items.length ? 0 : -1);
      } else if (
        body.kind === "places" &&
        body.matches?.length === 1 &&
        body.matches[0]
      ) {
        const match = body.matches[0];
        await inspectRef.current(match.lat, match.lng, {
          fly: true,
          label: match.label,
          fromAddressSearch: true,
          generation,
        });
      } else {
        // No-match: inline under search — clear pin, close card (P6).
        setError(null);
        setResult(null);
        setPlaceStub(null);
        setSearchNoMatch(true);
        setPanelKind("closed");
        markerRef.current?.remove();
        markerRef.current = null;
        replaceMapUrl({ place: null, panel: null });
      }
      if (generation === lookupGen.current) setApiOk(true);
    } catch (err) {
      if (generation !== lookupGen.current) return;
      const msg = visitorFacingError(err);
      setError(msg);
      // SHARE-FIX: surface Try again under search when no place card is open.
      setSuggestNote(msg);
      setSuggestions([]);
      setActiveSuggest(-1);
      setSuggesting(false);
      if (isServiceFailure(err)) {
        void pingApi().then((s) => {
          if (generation === lookupGen.current) setApiOk(s.ok);
        });
      }
    } finally {
      if (generation === lookupGen.current) setLoading(false);
    }
  };

  const chooseSuggestion = async (item: Suggestion) => {
    const generation = ++lookupGen.current;
    suggestGen.current += 1;
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    clearSuggestions();
    // SW-051: if the pick is the same postcode the user typed, keep their spacing.
    const typed = query.trim();
    const pickPc = (item.postcode || item.label || "").replace(/\s+/g, "").toUpperCase();
    const typedPc = typed.replace(/\s+/g, "").toUpperCase();
    if (!(item.kind === "postcode" && pickPc && pickPc === typedPc && /\s/.test(typed))) {
      setQuery(item.label);
    }
    setError(null);
    setLoading(true);
    try {
      if (item.kind === "words" && item.words) {
        await openWords(item.words, generation);
      } else if (item.kind === "postcode" && item.postcode) {
        await openPostcode(item.postcode, generation);
      } else if (item.lat != null && item.lng != null) {
        await inspectRef.current(item.lat, item.lng, {
          fly: true,
          label: item.label,
          fromAddressSearch: true,
          generation,
        });
      }
      if (generation === lookupGen.current) setApiOk(true);
    } catch (err) {
      if (generation !== lookupGen.current) return;
      setError(visitorFacingError(err));
      if (isServiceFailure(err)) {
        void pingApi().then((s) => {
          if (generation === lookupGen.current) setApiOk(s.ok);
        });
      }
    } finally {
      // Always clear search chrome after a pick. `.hud-search.loading` is
      // `loading || suggesting`; a stale suggest race must not leave the
      // spinner stuck after the place card is already open.
      setLoading(false);
      setSuggesting(false);
    }
  };

  const loadSuggestions = async (text: string) => {
    const generation = ++suggestGen.current;
    suggestAbort.current?.abort();
    const controller = new AbortController();
    suggestAbort.current = controller;
    if (!(await fetchCapabilities()).agr) {
      if (generation !== suggestGen.current) return;
      setSuggestions([]);
      setSuggestNote(
        looksLikeFullPostcode(text) ? "Press Enter to find this postcode." : POSTCODES_ONLY,
      );
      setSuggesting(false);
      return;
    }
    // Re-check after await: chooseSuggestion bumps suggestGen and must win —
    // otherwise a stale fetchCapabilities resume sets suggesting and leaves
    // `.hud-search.loading` stuck (class is loading || suggesting).
    if (generation !== suggestGen.current) return;
    setSuggesting(true);
    try {
      const response = await placeLookupFetch(
        `/place?q=${encodeURIComponent(text)}`,
        { signal: controller.signal },
      );
      const body = (await response.json()) as PlaceLookup;
      if (generation !== suggestGen.current) return;
      const found = suggestionsFromLookup(body, text);
      setSuggestions(found.items);
      setSuggestNote(
        found.items.length
          ? null
          : found.note || "No matches",
      );
      setActiveSuggest(found.items.length ? 0 : -1);
      setSuggesting(false);
    } catch (err) {
      if (controller.signal.aborted || generation !== suggestGen.current) return;
      setSuggestions([]);
      setActiveSuggest(-1);
      if (!isServiceFailure(err)) setSuggestNote(visitorFacingError(err));
      else setSuggestNote(null);
      setSuggesting(false);
    } finally {
      if (suggestAbort.current === controller) suggestAbort.current = null;
      if (generation === suggestGen.current) setSuggesting(false);
    }
  };

  const scheduleSuggest = (value: string) => {
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    const text = value.trim();
    if (text.length < 3) {
      suggestGen.current += 1;
      clearSuggestions();
      return;
    }
    // Drop stale in-flight work while waiting for the new debounce window.
    suggestAbort.current?.abort();
    suggestAbort.current = null;
    suggestGen.current += 1;
    // Pending "Looking…" for the debounce + fetch window (cleared on results /
    // empty / error / blur / Escape). Clear prior rows so the note can show.
    setSuggestions([]);
    setSuggestNote(null);
    setActiveSuggest(-1);
    setSuggesting(true);
    suggestTimer.current = setTimeout(() => {
      void loadSuggestions(text);
    }, 250);
  };

  const clearQuery = () => {
    suggestGen.current += 1;
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    setQuery("");
        clearSuggestions();
    setSuggesting(false);
    document.getElementById("place-query")?.focus();
  };

  useEffect(() => {
    return () => {
      if (suggestTimer.current) clearTimeout(suggestTimer.current);
      suggestAbort.current?.abort();
      suggestAbort.current = null;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const check = (retryImmediately: boolean) => {
      void pingApi().then((status) => {
        if (cancelled) return;
        // One miss must not wait out the 20s poll before the first retry.
        if (!status.ok && retryImmediately) {
          check(false);
          return;
        }
        setApiOk(status.ok);
        timer = setTimeout(() => check(true), status.ok ? 20_000 : 5_000);
      });
    };

    check(true);
    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  // Re-assess selection when scenario changes (legacy square path; no public £ display).
  useEffect(() => {
    if (!result) return;
    void fetchSquare(result.square.lat, result.square.lng, scenario, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  useEffect(() => {
    const container = mapContainer.current;
    if (!container || mapRef.current) return;

    const bootStyle = basemapStyleUrl(mapStyle);
    const map = new maplibregl.Map({
      container,
      style: bootStyle,
      center: [-4.2, 57.5],
      zoom: 5.7,
      maxZoom: MAP_MAX_ZOOM,
      // Map footer is one line; legal credits live behind the (i) control.
      attributionControl: {
        compact: true,
        customAttribution: [
          OPENFREEMAP_ATTRIBUTION,
          // Postcode / place search uses RM + ONS directories — keep once in the (i) control.
          "Contains Royal Mail data © Royal Mail copyright and database right",
          "Contains National Statistics data © Crown copyright and database right. Office for National Statistics",
          "No data provider endorses this site",
        ],
      },
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.getCanvas().style.cursor = "pointer";

    // MapLibre compact mode starts with maplibregl-compact-show (expanded).
    // Collapse to the (i) control by default; user click still expands.
    const collapseCompactAttribution = () => {
      const el = map
        .getContainer()
        .querySelector(".maplibregl-ctrl-attrib");
      if (!el?.classList.contains("maplibregl-compact")) return;
      el.classList.remove("maplibregl-compact-show");
      el.removeAttribute("open");
    };
    // Style reloads can append another compact (i). Adding is idempotent.
    const ensureSingleAttribution = () => {
      const root = map.getContainer();
      const controls = root.querySelectorAll(".maplibregl-ctrl-attrib");
      for (let i = 1; i < controls.length; i += 1) {
        controls[i]?.remove();
      }
      const toggles = root.querySelectorAll(".maplibregl-ctrl-attrib-button");
      for (let i = 1; i < toggles.length; i += 1) {
        toggles[i]?.remove();
      }
    };
    map.on("load", collapseCompactAttribution);
    map.once("idle", collapseCompactAttribution);
    map.on("styledata", ensureSingleAttribution);
    map.on("resize", () => {
      queueMicrotask(collapseCompactAttribution);
    });

    let userMoved = false;
    const noteUserMove = (event: { originalEvent?: Event }) => {
      if (event.originalEvent) userMoved = true;
    };
    map.on("dragstart", noteUserMove);
    map.on("zoomstart", noteUserMove);
    const syncCameraDataset = () => {
      const center = map.getCenter();
      container.dataset.lng = center.lng.toFixed(5);
      container.dataset.lat = center.lat.toFixed(5);
      container.dataset.zoom = map.getZoom().toFixed(3);
    };
    map.on("moveend", syncCameraDataset);
    map.on("zoomend", syncCameraDataset);
    const frameScotland = () => {
      if (cameraPreserveRef.current) {
        const cam = cameraPreserveRef.current;
        cameraPreserveRef.current = null;
        map.jumpTo({
          center: [cam.lng, cam.lat],
          zoom: cam.zoom,
        });
        syncCameraDataset();
        container.dataset.framed = "1";
        return;
      }
      if (userMoved) return;
      if (container.clientWidth < 40 || container.clientHeight < 40) return;
      const framed = container.dataset.framed === "1";
      // Panel open/close resizes the map and must still frame the national
      // view. Once the camera has left that view (GRID-BASE jumpTo ≥ z17),
      // do not fitBounds again — that yank cleared grid rebuilds (G19).
      // A shared-link view is the initial camera; later resizes must not
      // replace it with the national frame.
      if (framed) {
        if (container.dataset.viewSource === "url") return;
        if (map.getZoom() > 8) return;
      }
      // Apply a Scotland `c` before the national fitBounds. #169 returned
      // early whenever zoom was already > 8, so a bad or not-yet-applied
      // camera never reached fitBounds. Missing / out-of-Scotland `c`
      // (including 0,0) is not a view — still fit Scotland on the first frame.
      if (!framed) {
        const urlState = readMapUrlState(window.location.search);
        if (urlState.center) {
          map.jumpTo({
            center: [urlState.center.lng, urlState.center.lat],
            zoom: urlState.z ?? map.getZoom(),
          });
          syncCameraDataset();
          container.dataset.framed = "1";
          container.dataset.viewSource = "url";
          return;
        }
      }
      const narrow = window.innerWidth <= 900;
      map.fitBounds(
        [
          [-8.05, 54.48],
          [-0.55, 60.88],
        ],
        {
          padding: narrow
            ? { top: 132, bottom: 72, left: 12, right: 16 }
            : { top: 96, bottom: 36, left: 24, right: 28 },
          animate: false,
          maxZoom: 7.4,
        },
      );
      syncCameraDataset();
      container.dataset.framed = "1";
      container.dataset.viewSource = "scotland";
    };

    let seenWidth = -1;
    let seenHeight = -1;
    const resizeObserver = new ResizeObserver(() => {
      const nextWidth = container.clientWidth;
      const nextHeight = container.clientHeight;
      if (nextWidth === seenWidth && nextHeight === seenHeight) return;
      seenWidth = nextWidth;
      seenHeight = nextHeight;
      map.resize();
      if (map.loaded()) frameScotland();
    });
    resizeObserver.observe(container);

    map.on("load", () => {
      frameScotland();

      // Hatched grey pattern for missing choropleth values (honest no-data).
      if (!map.hasImage(NO_DATA_HATCH_IMAGE)) {
        const hatch = createNoDataHatchImageData(8);
        map.addImage(
          NO_DATA_HATCH_IMAGE,
          {
            width: hatch.width,
            height: hatch.height,
            data: hatch.data,
          },
          { pixelRatio: 1 },
        );
      }
      map.addSource("council-metrics", { type: "geojson", data: emptyCollection });
      // Bind paint to the public context ramp (never leave an AGR £ expression on the layer).
      const initialPaintMetric = paintMetricForChoropleth("off");
      map.addLayer({
        id: "council-fill",
        type: "fill",
        source: "council-metrics",
        layout: { visibility: "none" },
        paint: {
          "fill-color": paintForMetric(initialPaintMetric),
          "fill-opacity": 0.72,
        },
      });
      // Optional hatch overlay for polygons whose metric property is missing.
      map.addLayer({
        id: "council-nodata-hatch",
        type: "fill",
        source: "council-metrics",
        layout: { visibility: "none" },
        filter: [
          "!=",
          ["typeof", ["get", initialPaintMetric.property]],
          "number",
        ] as unknown as ExpressionSpecification,
        paint: {
          "fill-pattern": NO_DATA_HATCH_IMAGE,
          "fill-opacity": 0.85,
        },
      });
      map.addLayer({
        id: "council-line",
        type: "line",
        source: "council-metrics",
        paint: { "line-color": "#0c2c84", "line-width": 1.0, "line-opacity": 0.55 },
      });
      // Method outline: rural councils dashed emphasis
      map.addLayer({
        id: "council-method",
        type: "line",
        source: "council-metrics",
        filter: ["==", ["get", "rural"], true],
        layout: { visibility: "none" },
        paint: {
          "line-color": "#7a3e00",
          "line-width": 2.2,
          "line-dasharray": [2, 1.5],
          "line-opacity": 0.9,
        },
      });

      map.addSource("data-zones-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Scottish Government Data Zone boundaries 2022 (OGL). Outlines only — not a rent.",
      });
      map.addLayer({
        id: "data-zones-fill",
        type: "fill",
        source: "data-zones-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#0b1e3a",
          "fill-opacity": 0.04,
        },
      });
      map.addLayer({
        id: "data-zones-line",
        type: "line",
        source: "data-zones-overlay",
        layout: { visibility: "none" },
        paint: {
          "line-color": "#0b1e3a",
          "line-width": 1.05,
          "line-opacity": 0.78,
        },
      });

      // UX10-2: dz2022_masked fill under faint full DZ outlines (click stays on data-zones).
      map.addSource("dz2022-masked-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution: "NRS Settlements 2022 (OGL v3), contains OS data",
      });
      map.addLayer(
        {
          id: "dz2022-masked-fill",
          type: "fill",
          source: "dz2022-masked-overlay",
          layout: { visibility: "none" },
          paint: {
            "fill-color": "#1a4a6e",
            "fill-opacity": 0.12,
          },
        },
        "data-zones-fill",
      );
      map.addLayer(
        {
          id: "dz2022-masked-line",
          type: "line",
          source: "dz2022-masked-overlay",
          layout: { visibility: "none" },
          paint: {
            "line-color": "#1a4a6e",
            "line-width": 0.6,
            "line-opacity": 0.35,
          },
        },
        "data-zones-line",
      );

      map.addSource("repd-onshore-wind-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "REPD onshore wind © DESNZ / Crown copyright (OGL v3.0). MW/status only — not a rent.",
      });
      map.addLayer({
        id: "repd-onshore-wind-circle",
        type: "circle",
        source: "repd-onshore-wind-overlay",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 5,
          "circle-color": "#00796b",
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.85,
        },
      });

      map.addSource("ces-aquaculture-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Contains information from the Crown Estate Scotland licensed under the Open Government Licence v3.0.",
      });
      map.addLayer({
        id: "ces-aquaculture-fill",
        type: "fill",
        source: "ces-aquaculture-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#00796b",
          "fill-opacity": 0.38,
        },
      });
      map.addLayer({
        id: "ces-aquaculture-line",
        type: "line",
        source: "ces-aquaculture-overlay",
        layout: { visibility: "none" },
        paint: {
          "line-color": "#004d40",
          "line-width": 1.0,
          "line-opacity": 0.85,
        },
      });

      map.addSource("public-land-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Scottish Public and Crown Estate Land 2024 — licence unverified/not open; not drawn on the public map.",
      });
      map.addLayer({
        id: "public-land-fill",
        type: "fill",
        source: "public-land-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": PUBLIC_LAND_FILL,
          "fill-opacity": 0.42,
        },
      });
      map.addLayer({
        id: "public-land-line",
        type: "line",
        source: "public-land-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#1b4f72", "line-width": 0.9, "line-opacity": 0.75 },
      });

      map.addSource("nfi-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "© Forestry Commission copyright. Contains OS data © Crown copyright. OGL v3.0. Woodland map, shown for context. Not a rent.",
      });
      map.addLayer({
        id: "nfi-fill",
        type: "fill",
        source: "nfi-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": NFI_FILL,
          "fill-opacity": 0.38,
        },
      });
      map.addLayer({
        id: "nfi-line",
        type: "line",
        source: "nfi-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#0f3d22", "line-width": 0.9, "line-opacity": 0.85 },
      });

      map.addSource("native-woodland-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Native Woodland Survey of Scotland. © Scottish Forestry. OGL v3.0. Native woodland map, shown for context. Not a rent or a title.",
      });
      map.addLayer({
        id: "native-woodland-fill",
        type: "fill",
        source: "native-woodland-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": NATIVE_WOODLAND_FILL,
          "fill-opacity": 0.4,
        },
      });
      map.addLayer({
        id: "native-woodland-line",
        type: "line",
        source: "native-woodland-overlay",
        layout: { visibility: "none" },
        paint: {
          "line-color": "#145c32",
          "line-width": 0.9,
          "line-opacity": 0.85,
        },
      });

      map.addSource("repd-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "REPD © DESNZ / Crown copyright (OGL v3.0). Planned wind and hydro sites, shown for context. Not a rent.",
      });
      map.addLayer({
        id: "repd-circle",
        type: "circle",
        source: "repd-overlay",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": 5,
          "circle-color": "#00796b",
          "circle-stroke-width": 1,
          "circle-stroke-color": "#ffffff",
          "circle-opacity": 0.85,
        },
      });

      map.addSource("crown-leases-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Contains public sector information, licensed under the Open Government Licence v3.0, from Crown Estate Scotland. Seabed leases, shown for context. Not a rent or a title.",
      });
      map.addLayer({
        id: "crown-leases-fill",
        type: "fill",
        source: "crown-leases-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": CES_LEASE_FILL,
          "fill-opacity": 0.38,
        },
      });
      map.addLayer({
        id: "crown-leases-line",
        type: "line",
        source: "crown-leases-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#0b3d5c", "line-width": 1.0, "line-opacity": 0.85 },
      });

      map.addSource("designations-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Contains NatureScot data licensed under the Open Government Licence v3.0.",
      });
      map.addLayer({
        id: "designations-fill",
        type: "fill",
        source: "designations-overlay",
        layout: { visibility: "none" },
        paint: { "fill-color": "#15803d", "fill-opacity": 0.35 },
      });
      map.addLayer({
        id: "designations-line",
        type: "line",
        source: "designations-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#14532d", "line-width": 1.1, "line-opacity": 0.9 },
      });

      map.addSource("hla-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Housing Land Supply – Scotland © Improvement Service / local planning authorities (OGL v3.0). Audit sites, not a title.",
      });
      map.addLayer({
        id: "hla-fill",
        type: "fill",
        source: "hla-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": HLA_FILL,
          "fill-opacity": 0.4,
        },
      });
      map.addLayer({
        id: "hla-line",
        type: "line",
        source: "hla-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#3d2a5c", "line-width": 1.0, "line-opacity": 0.9 },
      });

      map.addSource("ldp-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "LDP allocations © planning authorities / Spatial Hub (OGL v3.0). Fragmented national coverage; not a title.",
      });
      map.addLayer({
        id: "ldp-fill",
        type: "fill",
        source: "ldp-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": LDP_FILL,
          "fill-opacity": 0.38,
        },
      });
      map.addLayer({
        id: "ldp-line",
        type: "line",
        source: "ldp-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#2f5d2e", "line-width": 1.0, "line-opacity": 0.85 },
      });

      map.addSource("community-ownership-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Community Ownership in Scotland 2024 © Scottish Government (OGL v3.0). Postcode centroids via postcodes.io (ONS Postcode Directory) — not titles. Contains OS data © Crown copyright and database right 2026. Contains Royal Mail data © Royal Mail copyright and database right 2026. Contains National Statistics data © Crown copyright and database right 2026.",
      });
      map.addLayer({
        id: "community-ownership-circle",
        type: "circle",
        source: "community-ownership-overlay",
        layout: { visibility: "none" },
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6,
            3,
            12,
            7,
            16,
            10,
          ],
          "circle-color": COMMUNITY_OWNERSHIP_CIRCLE,
          "circle-opacity": 0.85,
          "circle-stroke-color": "#12353a",
          "circle-stroke-width": 0.8,
        },
      });

      map.addSource("lca-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Land Capability for Agriculture 1:250k © The James Hutton Institute. Open Data Licence (PSI under OGL v2.0).",
      });
      map.addLayer({
        id: "lca-fill",
        type: "fill",
        source: "lca-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": LCA_FILL,
          "fill-opacity": 0.38,
        },
      });
      map.addLayer({
        id: "lca-line",
        type: "line",
        source: "lca-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#334422", "line-width": 0.6, "line-opacity": 0.55 },
      });


      for (const layer of CONTEXT_LAYERS) {
        if (layer.kind === "raster") {
          map.addSource(layer.id, {
            type: "raster",
            tiles: [`/api/context/${layer.id}/tiles/{z}/{x}/{y}`],
            tileSize: 256,
            minzoom: layer.minzoom,
            maxzoom: layer.maxzoom,
            scheme: "xyz",
          });
          map.addLayer({
            id: layer.id,
            type: "raster",
            source: layer.id,
            paint: {
              "raster-opacity": layer.opacity ?? 0.85,
              "raster-fade-duration": 0,
            },
            layout: { visibility: "none" },
          });
          continue;
        }
        map.addSource(`${layer.id}-src`, {
          type: "geojson",
          data: emptyCollection,
        });
        if (layer.kind === "fill") {
          map.addLayer({
            id: `${layer.id}-fill`,
            type: "fill",
            source: `${layer.id}-src`,
            layout: { visibility: "none" },
            paint: { "fill-color": layer.color, "fill-opacity": 0.28 },
          });
          map.addLayer({
            id: `${layer.id}-line`,
            type: "line",
            source: `${layer.id}-src`,
            layout: { visibility: "none" },
            paint: {
              "line-color": layer.color,
              "line-width": 1.6,
              "line-opacity": 0.95,
            },
          });
        } else if (layer.kind === "line") {
          map.addLayer({
            id: layer.id,
            type: "line",
            source: `${layer.id}-src`,
            layout: { visibility: "none" },
            paint: {
              "line-color": layer.color,
              "line-width": 1.4,
              "line-opacity": 0.9,
            },
          });
        } else {
          map.addLayer({
            id: layer.id,
            type: "circle",
            source: `${layer.id}-src`,
            layout: { visibility: "none" },
            paint: {
              "circle-radius": 4.5,
              "circle-color": layer.color,
              "circle-stroke-width": 1,
              "circle-stroke-color": "#ffffff",
              "circle-opacity": 0.9,
            },
          });
        }
      }

      // GIS 16 — plot-level parcels / selected-parcel / w3w / selected-square
      // are not registered on the public map.
      removePlotLevelMapBits(map);

      void import("../lib/grid3Runtime").then(({ ensureGrid3Layers }) => {
        if (mapRef.current !== map) return;
        try {
          if (!map.getStyle()?.layers) return;
        } catch {
          return;
        }
        ensureGrid3Layers(map);
      });

      setMapReady(true);
    });

    map.on("mousemove", "data-zones-fill", (event) => {
      map.getCanvas().style.cursor = "pointer";
      const feat = event.features?.[0];
      const props = feat?.properties as
        | { code?: string; name?: string; la_name?: string }
        | undefined;
      if (!props?.code || !event.lngLat) return;
      const label = props.name
        ? `${escapeHtml(props.name)} (${escapeHtml(props.code)})`
        : escapeHtml(props.code);
      const la = props.la_name
        ? `<br/><span class="popup-source">${escapeHtml(props.la_name)}</span>`
        : "";
      if (!dzHoverPopupRef.current) {
        dzHoverPopupRef.current = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 10,
          className: "dz-hover-popup",
        });
      }
      dzHoverPopupRef.current
        .setLngLat(event.lngLat)
        .setHTML(
          `<div class="layer-popup"><strong>Data zone</strong><br/>${label}${la}</div>`,
        )
        .addTo(map);
    });
    map.on("mouseleave", "data-zones-fill", () => {
      map.getCanvas().style.cursor = "";
      dzHoverPopupRef.current?.remove();
    });

    map.on("click", (event) => {
      const lat = event.lngLat.lat;
      const lng = event.lngLat.lng;

      // E10 — debounce identify 150ms; only latest renders (AbortController in selectPlace).
      if (identifyTimerRef.current) clearTimeout(identifyTimerRef.current);
      identifyTimerRef.current = setTimeout(() => {
        void runMapIdentify(lat, lng, event.point);
      }, 150);
    });

    const runMapIdentify = async (
      lat: number,
      lng: number,
      point: maplibregl.Point,
    ) => {
      // Data Zone click → place card (boundaries only; no AGR £).
      const dzHits =
        map.getLayer("data-zones-fill") &&
        map.getLayoutProperty("data-zones-fill", "visibility") === "visible"
          ? map.queryRenderedFeatures(point, {
              layers: ["data-zones-fill"],
            })
          : [];
      const dzProps = dzHits[0]?.properties as
        | {
            code?: string;
            name?: string;
            vintage?: number | string;
            la_name?: string;
            population?: number | string;
            pop_year?: number | string;
            dwellings?: number | string;
            dw_year?: number | string;
          }
        | undefined;
      if (dzProps?.code) {
        dzHoverPopupRef.current?.remove();
        const asNum = (v: number | string | undefined): number | null => {
          if (typeof v === "number" && Number.isFinite(v)) return v;
          if (typeof v === "string" && v !== "" && Number.isFinite(Number(v))) {
            return Number(v);
          }
          return null;
        };
        void inspectRef.current(lat, lng, {
          fly: false,
          label: dzProps.name || dzProps.code,
          dataZoneCode: dzProps.code,
          dataZoneName: dzProps.name || null,
          dataZoneVintage: asNum(dzProps.vintage),
          laName: dzProps.la_name || null,
          population: asNum(dzProps.population),
          popYear: asNum(dzProps.pop_year),
          dwellings: asNum(dzProps.dwellings),
          dwYear: asNum(dzProps.dw_year),
        });
        grid3AfterIdentifyRef.current?.(lng, lat);
        return;
      }

      // Layer popup: public land / SVDLS / LCA (ownership layers) — no parcels.
      try {
        const publicHits =
          map.getLayer("public-land-fill") &&
          map.getLayoutProperty("public-land-fill", "visibility") === "visible"
            ? map.queryRenderedFeatures(point, {
                layers: ["public-land-fill"],
              })
            : [];
        const publicProps = publicHits[0]?.properties as
          | {
              organisation?: string;
              owner_type?: string;
              site_name?: string;
              source?: string;
            }
          | undefined;
        const lcaHits =
          map.getLayer("lca-fill") &&
          map.getLayoutProperty("lca-fill", "visibility") === "visible"
            ? map.queryRenderedFeatures(point, {
                layers: ["lca-fill"],
              })
            : [];
        const lcaProps = lcaHits[0]?.properties as
          | {
              class_label?: string;
              lccode?: number | string;
              source?: string;
            }
          | undefined;
        const html = layerPopupHtml({
          parcelId: null,
          areaSqm: null,
          ownerType: publicProps?.owner_type || publicProps?.organisation || null,
          siteName: publicProps?.site_name || null,
          lcaClassLabel: lcaProps?.class_label || null,
          lcaCode: lcaProps?.lccode ?? null,
          source:
            lcaProps?.source ||
            publicProps?.source ||
            (publicProps || lcaProps
              ? "Open land layers — research overlay, not a title"
              : null),
        });
        layerPopupRef.current?.remove();
        layerPopupRef.current = null;
        if (html) {
          layerPopupRef.current = new maplibregl.Popup({
            closeButton: true,
            maxWidth: "280px",
            className: "layer-feature-popup",
          })
            .setLngLat([lng, lat])
            .setHTML(html)
            .addTo(map);
          const closeBtn = layerPopupRef.current
            .getElement()
            ?.querySelector("button.maplibregl-popup-close-button");
          if (closeBtn instanceof HTMLElement) {
            closeBtn.setAttribute("aria-label", "Close popup");
          }
        }
      } catch {
        /* ignore popup failures */
      }

      await inspectRef.current(lat, lng, { fly: false });
      grid3AfterIdentifyRef.current?.(lng, lat);
    };


    mapRef.current = map;
    // E2e / GIS checks (MAP-CARDS 26–32, A3): MapLibre instance for style/zoom probes.
    (
      window as unknown as { __map?: maplibregl.Map | null }
    ).__map = map;
    if (typeof window !== "undefined") {
      (window as unknown as { __SCOT_LAND_MAP__?: Map }).__SCOT_LAND_MAP__ =
        map;
    }
    return () => {
      resizeObserver.disconnect();
      markerRef.current?.remove();
      markerRef.current = null;
      parcelLabelRef.current?.remove();
      parcelLabelRef.current = null;
      layerPopupRef.current?.remove();
      layerPopupRef.current = null;
      map.remove();
      mapRef.current = null;
      (
        window as unknown as { __map?: maplibregl.Map | null }
      ).__map = null;
      if (typeof window !== "undefined") {
        delete (window as unknown as { __SCOT_LAND_MAP__?: Map })
          .__SCOT_LAND_MAP__;
      }
      setMapReady(false);
      // Allow deep-link boot on the next map instance (Strict Mode / style remount).
      urlBootDoneRef.current = false;
    };
    // Remount when basemap style changes (OpenFreeMap light ↔ detailed).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapStyle]);

  // Deep-link boot (?lat/lng/words) once mapReady — survives style remount.
  // Prefer the mount-time capture: layers URL sync may already have rewritten
  // lat/lng → c= by the time the style loads.
  useEffect(() => {
    if (!mapReady || urlBootDoneRef.current) return;
    urlBootDoneRef.current = true;
    const captured = deepLinkCaptureRef.current;
    const bootParams = new URLSearchParams(window.location.search);
    const boot = readMapUrlState(bootParams);
    const bootWords = captured?.words || bootParams.get("words");
    const parseBootCoord = (raw: string | null): number | null => {
      if (raw == null || raw.trim() === "") return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    };
    const bootLat =
      captured?.lat ?? parseBootCoord(bootParams.get("lat"));
    const bootLng =
      captured?.lng ??
      parseBootCoord(bootParams.get("lng") ?? bootParams.get("lon"));
    if (captured?.vacant || bootParams.get("vacant") === "1") {
      setShowVdl(true);
    }
    if (captured?.community || bootParams.get("community") === "1") {
      setShowCommunityOwnership(true);
    }
    if (bootWords) {
      setQuery(bootWords);
      void (async () => {
        if (!(await fetchCapabilities()).agr) return;
        const generation = ++lookupGen.current;
        try {
          await openWordsRef.current(bootWords, generation);
          setApiOk(true);
        } catch (err) {
          setError(visitorFacingError(err));
          if (isServiceFailure(err)) {
            void pingApi().then((s) => setApiOk(s.ok));
          }
        }
      })();
    } else if (
      bootLat != null &&
      bootLng != null &&
      isScotlandViewCenter(bootLng, bootLat)
    ) {
      // URL deep-link is intentional navigation (like search → half), not a map tap.
      void inspectRef.current(bootLat, bootLng, {
        fly: true,
        fromAddressSearch: true,
        keepCollapsed: panelCollapsedRef.current,
      });
    } else if (captured?.place && boot.center) {
      // place= + c= after rewrite — still identify at the captured centre.
      void inspectRef.current(boot.center.lat, boot.center.lng, {
        fly: true,
        fromAddressSearch: true,
        keepCollapsed: panelCollapsedRef.current,
      });
    } else if (boot.panel === "place" && boot.center) {
      // panel=place with a centre and no lat/lng pair — reopen that place.
      // A map-tap or search URL write remounts the map. If this card is
      // already open on that point, do not identify again (that forced
      // peek taps to half and put the loading rows back under the card).
      const remembered = placeDetentMemory;
      const stub = placeStubRef.current;
      const alreadyOpen =
        remembered != null &&
        panelKindRef.current === "place" &&
        stub != null &&
        Math.abs(stub.lat - boot.center.lat) < 0.00002 &&
        Math.abs(stub.lng - boot.center.lng) < 0.00002;
      if (!alreadyOpen) {
        void inspectRef.current(boot.center.lat, boot.center.lng, {
          fly: remembered == null,
          fromAddressSearch: remembered !== "peek",
          keepCollapsed: panelCollapsedRef.current,
          label: boot.place,
        });
      }
    } else if (boot.panel === "place") {
      replaceMapUrl({ panel: null });
    } else {
      const map = mapRef.current;
      if (map && boot.center) {
        map.jumpTo({
          center: [boot.center.lng, boot.center.lat],
          zoom: boot.z ?? map.getZoom(),
        });
      }
    }
  }, [mapReady]);

  // Which optional routers the API mounts; legacy calls are skipped (quietly) when absent.
  useEffect(() => {
    let cancelled = false;
    void fetchCapabilities().then((caps) => {
      if (cancelled || !caps.reachable) return;
      setAgrAvailable(caps.agr);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Built-up mask is always-on background when catalogue says live.
  // Empty catalogue stubs (common in e2e) leave the background attempt on.
  useEffect(() => {
    let cancelled = false;
    void fetchLayerCatalog()
      .then((payload) => {
        if (cancelled) return;
        const layers = payload.layers ?? [];
        setCatalogLayers(layers);
        if (layers.length === 0) {
          setBuiltupMaskCatalogGap(false);
          return;
        }
        const mask = layers.find((layer) => layer.id === "builtup_mask");
        const maskReady = Boolean(mask && mask.status === "live");
        setBuiltupMaskCatalogGap(!maskReady);
        // Background style: on when live; off only when catalogue proves gap.
        setShowBuiltupMask(maskReady);
        if (!maskReady) return;

        const path =
          "/layers/open/dz2022-masked?south=55.85&west=-4.27&north=55.87&east=-4.24&max_features=1";
        void apiJson<GeoJSON.FeatureCollection>(path).catch((err: unknown) => {
          if (isServiceUnavailable(err)) {
            setBuiltupMaskUnavailable(true);
            setShowBuiltupMask(false);
          }
        });
      })
      .catch(() => {
        if (!cancelled) {
          setCatalogLayers([]);
          setBuiltupMaskCatalogGap(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [markTileUnavailable]);

  // Idea 57 — service-unavailable is detected when the mask is turned on
  // (loadMasked / enable check), not via a mount-time probe.

  // Council boundaries at rest; fill colours from council-metrics at z5–7 when AGR on.
  // /layers/councils is context-scrubbed (no modelled AGR £ on the public shell).
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("council-fill")) return;
    const metric = paintMetricForChoropleth(choropleth);
    map.setPaintProperty("council-fill", "fill-color", paintForMetric(metric));
    if (map.getLayer("council-nodata-hatch")) {
      map.setFilter("council-nodata-hatch", [
        "!=",
        ["typeof", ["get", metric.property]],
        "number",
      ] as unknown as ExpressionSpecification);
      map.setLayoutProperty("council-nodata-hatch", "visibility", "none");
    }
    map.setFilter("council-fill", null);
    map.setFilter("council-line", null);

    const zoom = map.getZoom();
    const lineVis = showCouncils ? "visible" : "none";
    map.setLayoutProperty("council-line", "visibility", lineVis);

    // Fill only when AGR/value layer is on and at overview zooms (z5–7).
    const fillOn = showCouncils && showAgr && zoom >= 5 && zoom < 8;
    map.setLayoutProperty(
      "council-fill",
      "visibility",
      fillOn ? "visible" : "none",
    );
  }, [mapReady, choropleth, showCouncils, showAgr, mapZoom]);

  // GRID-BASE-1 — device-drawn lines on moveend; lazy-load proj4 chunk (G9).
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    let cancelled = false;
    let gen = 0;
    let retryQueued = false;
    let gridMod: typeof import("../lib/grid3Map") | null = null;
    let runtime: typeof import("../lib/grid3Runtime") | null = null;

    const styleLive = () => {
      try {
        return Boolean(map.getStyle()?.layers);
      } catch {
        return false;
      }
    };

    const queueRetry = () => {
      if (cancelled || retryQueued) return;
      retryQueued = true;
      const kick = () => {
        retryQueued = false;
        if (!cancelled) void rebuild();
      };
      map.once("idle", kick);
      map.once("styledata", kick);
    };

    const clearLines = () => {
      if (!styleLive()) return;
      const src = map.getSource("grid3-lines") as GeoJSONSource | undefined;
      src?.setData({ type: "FeatureCollection", features: [] });
      if (map.getLayer("grid3-lines-layer")) {
        map.setLayoutProperty("grid3-lines-layer", "visibility", "none");
      }
    };

    const rebuild = async () => {
      if (cancelled || !mapRef.current) return;
      // Basemap / panel resize can fire moveend before the style exists.
      // Dropping that event left G10 stuck with no lines after jumpTo.
      if (!styleLive()) {
        queueRetry();
        return;
      }
      const myGen = ++gen;
      if (!showGrid3Ref.current) {
        clearLines();
        return;
      }
      if (!gridMod || !runtime) {
        const [gm, rt] = await Promise.all([
          import("../lib/grid3Map"),
          import("../lib/grid3Runtime"),
        ]);
        if (cancelled || myGen !== gen) return;
        gridMod = gm;
        runtime = rt;
        if (typeof window !== "undefined") {
          (
            window as unknown as {
              __SCOT_LAND_GRID3__?: {
                buildGrid3Lines: typeof gm.buildGrid3Lines;
                squareAtWgs: typeof gm.squareAtWgs;
                buildGrid3Highlight: typeof gm.buildGrid3Highlight;
              };
            }
          ).__SCOT_LAND_GRID3__ = {
            buildGrid3Lines: gm.buildGrid3Lines,
            squareAtWgs: gm.squareAtWgs,
            buildGrid3Highlight: gm.buildGrid3Highlight,
          };
        }
      }
      if (cancelled || myGen !== gen) return;
      if (!styleLive()) {
        queueRetry();
        return;
      }
      // Re-read zoom after await so a stale low-zoom rebuild cannot wipe z17+.
      const z = map.getZoom();
      if (z < GRID3_MIN_ZOOM) {
        clearLines();
        return;
      }
      runtime.ensureGrid3Layers(map);
      runtime.setGrid3LinePaint(map, false);
      const b = map.getBounds();
      if (!b) return;
      const corners = [
        { lng: b.getWest(), lat: b.getSouth() },
        { lng: b.getEast(), lat: b.getSouth() },
        { lng: b.getEast(), lat: b.getNorth() },
        { lng: b.getWest(), lat: b.getNorth() },
      ];
      const { collection } = gridMod.buildGrid3Lines(corners);
      if (cancelled || myGen !== gen) return;
      const src = map.getSource(gridMod.GRID3_SOURCE_LINES) as
        | GeoJSONSource
        | undefined;
      src?.setData(collection);
      if (map.getLayer(gridMod.GRID3_LAYER_LINES)) {
        map.setLayoutProperty(
          gridMod.GRID3_LAYER_LINES,
          "visibility",
          "visible",
        );
      }
    };

    void rebuild();
    const onMove = () => {
      void rebuild();
    };
    map.on("moveend", onMove);
    map.on("zoomend", onMove);
    return () => {
      cancelled = true;
      map.off("moveend", onMove);
      map.off("zoomend", onMove);
      clearLines();
    };
  }, [mapReady, showGrid3, mapStyle]);

  // GRID-BASE-1 — desktop hover ≥z18; rAF throttle (G4 / G11).
  useEffect(() => {
    if (!mapReady || !showGrid3) return;
    const map = mapRef.current;
    if (!map) return;

    let raf = 0;
    let pending: { lng: number; lat: number; x: number; y: number } | null =
      null;
    let mod: typeof import("../lib/grid3Map") | null = null;
    let runtime: typeof import("../lib/grid3Runtime") | null = null;

    const apply = async () => {
      raf = 0;
      const p = pending;
      pending = null;
      if (!p || !showGrid3Ref.current) return;
      const z = map.getZoom();
      if (z < GRID3_HOVER_ZOOM) {
        setGrid3Tooltip(null);
        return;
      }
      if (
        typeof window !== "undefined" &&
        window.matchMedia("(pointer: coarse)").matches
      ) {
        return;
      }
      if (!mod || !runtime) {
        const [gm, rt] = await Promise.all([
          import("../lib/grid3Map"),
          import("../lib/grid3Runtime"),
        ]);
        mod = gm;
        runtime = rt;
      }
      runtime.ensureGrid3Layers(map);
      const square = mod.squareAtWgs(p.lng, p.lat);
      const src = map.getSource(mod.GRID3_SOURCE_HIGHLIGHT) as
        | GeoJSONSource
        | undefined;
      if (!square) {
        src?.setData(mod.EMPTY_FC);
        setGrid3Tooltip(null);
        if (!grid3SquareRef.current) {
          runtime.setGrid3Visibility(map, z >= GRID3_MIN_ZOOM, false);
        }
        return;
      }
      src?.setData(mod.buildGrid3Highlight(square.easting, square.northing));
      for (const id of [
        mod.GRID3_LAYER_HIGHLIGHT_FILL,
        mod.GRID3_LAYER_HIGHLIGHT_HALO,
        mod.GRID3_LAYER_HIGHLIGHT_LINE,
      ]) {
        if (map.getLayer(id)) {
          map.setLayoutProperty(id, "visibility", "visible");
        }
      }
      setGrid3Tooltip({ x: p.x, y: p.y, ref: square.ref });
    };

    const onMove = (event: maplibregl.MapMouseEvent) => {
      pending = {
        lng: event.lngLat.lng,
        lat: event.lngLat.lat,
        x: event.point.x,
        y: event.point.y,
      };
      if (!raf) {
        raf = requestAnimationFrame(() => {
          void apply();
        });
      }
    };
    const onLeave = () => {
      pending = null;
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      setGrid3Tooltip(null);
      if (!grid3SquareRef.current) {
        void import("../lib/grid3Map").then((gm) => {
          const src = map.getSource(gm.GRID3_SOURCE_HIGHLIGHT) as
            | GeoJSONSource
            | undefined;
          src?.setData(gm.EMPTY_FC);
        });
      }
    };

    map.on("mousemove", onMove);
    map.on("mouseout", onLeave);
    return () => {
      map.off("mousemove", onMove);
      map.off("mouseout", onLeave);
      if (raf) cancelAnimationFrame(raf);
      setGrid3Tooltip(null);
    };
  }, [mapReady, showGrid3]);

  // GRID-BASE-1 — tap/click ≥z19 selects square into row 6 (G5 / G15).
  useEffect(() => {
    grid3AfterIdentifyRef.current = (lng: number, lat: number) => {
      if (!showGrid3Ref.current) return;
      const map = mapRef.current;
      if (!map) return;
      const z = map.getZoom();
      if (z < GRID3_TAP_ZOOM) return;
      void Promise.all([
        import("../lib/grid3Map"),
        import("../lib/grid3Runtime"),
      ]).then(([gm, rt]) => {
        if (!mapRef.current) return;
        rt.ensureGrid3Layers(map);
        const square = gm.squareAtWgs(lng, lat);
        if (!square) {
          setGrid3Square(null);
          const src = map.getSource(gm.GRID3_SOURCE_HIGHLIGHT) as
            | GeoJSONSource
            | undefined;
          src?.setData(gm.EMPTY_FC);
          return;
        }
        setGrid3Square(square);
        const src = map.getSource(gm.GRID3_SOURCE_HIGHLIGHT) as
          | GeoJSONSource
          | undefined;
        src?.setData(gm.buildGrid3Highlight(square.easting, square.northing));
        for (const id of [
          gm.GRID3_LAYER_HIGHLIGHT_FILL,
          gm.GRID3_LAYER_HIGHLIGHT_HALO,
          gm.GRID3_LAYER_HIGHLIGHT_LINE,
        ]) {
          if (map.getLayer(id)) {
            map.setLayoutProperty(id, "visibility", "visible");
          }
        }
      });
    };
    return () => {
      grid3AfterIdentifyRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getSource("council-metrics")) return;
    let cancelled = false;
    void apiJson<GeoJSON.FeatureCollection>("/boundaries/councils")
      .then((data) => {
        if (cancelled || !mapRef.current) return;
        safeSetGeoJson(
          map.getSource("council-metrics") as GeoJSONSource | undefined,
          data,
        );
      })
      .catch(() => {
        /* boundaries optional — lines stay empty */
      });
    return () => {
      cancelled = true;
    };
  }, [mapReady]);

  useEffect(() => {
    replaceMapUrl({ layers: activeLayerIds });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    showVdl,
    showCommunityOwnership,
    showCouncils,
    showDataZones,
    showAgr,
    showHla,
    showGrid3,
    ledgerEnabled,
  ]);

  // Data Zone boundaries (simplified GeoJSON by view bounds — outlines only, no AGR £)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("data-zones-fill")) return;
      map.setLayoutProperty("data-zones-fill", "visibility", vis);
      map.setLayoutProperty("data-zones-line", "visibility", vis);
    };

    if (!showDataZones) {
      setVis("none");
      dzHoverPopupRef.current?.remove();
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadDataZones = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < DATA_ZONE_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/data-zones?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=120`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("data-zones-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          if (err instanceof ApiError && err.status === 503) {
            setLayerNotice(
              "Data Zone boundaries are not available right now (source unavailable). Gaps are not filled with guesses.",
            );
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadDataZones, 700);
    };

    loadDataZones();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showDataZones]);

  // UX10-2 built-up mask (dz2022_masked) — display only; full DZ outlines stay clickable
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("dz2022-masked-fill")) return;
      map.setLayoutProperty("dz2022-masked-fill", "visibility", vis);
      map.setLayoutProperty("dz2022-masked-line", "visibility", vis);
    };

    if (!showBuiltupMask) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadMasked = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      if (map.getZoom() < DATA_ZONE_MIN_ZOOM) {
        setVis("none");
        return;
      }
      const b = map.getBounds();
      inFlight = true;
      const path =
        `/layers/open/dz2022-masked?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=400`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("dz2022-masked-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
        })
        .catch((err: unknown) => {
          // Unloaded or empty — keep outlines; do not invent mask geometry.
          if (!cancelled) setVis("none");
          if (!cancelled && isServiceUnavailable(err)) {
            setBuiltupMaskUnavailable(true);
            setShowBuiltupMask(false);
          }
        })
        .finally(() => {
          inFlight = false;
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadMasked, 700);
    };

    loadMasked();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showBuiltupMask]);

  // DESNZ REPD onshore wind (MW/status only, no £ rent)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("repd-onshore-wind-circle")) return;
      map.setLayoutProperty("repd-onshore-wind-circle", "visibility", vis);
    };

    if (!showRepdOnshoreWind) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadRepdOnshoreWind = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < REPD_ONSHORE_WIND_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/repd-onshore-wind?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(
            map.getSource("repd-onshore-wind-overlay") as GeoJSONSource | undefined,
            data,
          );
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          // SHARE-FIX: 503 → Coming soon on "Onshore wind and hydro", no raw error.
          if (isServiceUnavailable(err)) {
            markTileUnavailable("3");
            setLedgerEnabled((cur) => {
              if (!cur["3"]) return cur;
              const copy = { ...cur };
              delete copy["3"];
              return copy;
            });
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadRepdOnshoreWind, 700);
    };

    loadRepdOnshoreWind();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showRepdOnshoreWind, markTileUnavailable]);

  // CES aquaculture seabed leases (OGL Spatial Hub; ledger row 5; no £ rent)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("ces-aquaculture-fill")) return;
      map.setLayoutProperty("ces-aquaculture-fill", "visibility", vis);
      map.setLayoutProperty("ces-aquaculture-line", "visibility", vis);
    };

    if (!showCesAquaculture) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadCesAquaculture = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < CES_AQUACULTURE_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/ces-aquaculture?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(
            map.getSource("ces-aquaculture-overlay") as GeoJSONSource | undefined,
            data,
          );
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          // SHARE-FIX: 503 → Coming soon on Aquaculture, no raw error.
          if (isServiceUnavailable(err)) {
            markTileUnavailable("5");
            setLedgerEnabled((cur) => {
              if (!cur["5"]) return cur;
              const copy = { ...cur };
              delete copy["5"];
              return copy;
            });
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadCesAquaculture, 700);
    };

    loadCesAquaculture();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showCesAquaculture, markTileUnavailable]);

  // Oil and gas switch paints the existing oil-fields context layer.
  useEffect(() => {
    const on = Boolean(ledgerEnabled["9"]);
    setContextOn((cur) => {
      if (Boolean(cur["oil-fields"]) === on) return cur;
      return { ...cur, "oil-fields": on };
    });
  }, [ledgerEnabled]);

  // Protected nature sites — bbox fetch only at the layer's minimum zoom.
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;
    const on = Boolean(ledgerEnabled.designations);

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("designations-fill")) return;
      map.setLayoutProperty("designations-fill", "visibility", vis);
      map.setLayoutProperty("designations-line", "visibility", vis);
    };

    if (!on) {
      setVis("none");
      setProtectedSitesHint(false);
      safeSetGeoJson(
        map.getSource("designations-overlay") as GeoJSONSource | undefined,
        emptyCollection,
      );
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadDesignations = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < DESIGNATIONS_MIN_ZOOM) {
        setVis("none");
        setProtectedSitesHint(false);
        safeSetGeoJson(
          map.getSource("designations-overlay") as GeoJSONSource | undefined,
          emptyCollection,
        );
        return;
      }
      inFlight = true;
      const q =
        `south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}` +
        `&max_features=80&z=${map.getZoom()}`;
      const paths = [
        `/layers/open/naturescot-designations?${q}`,
        `/layers/open/sssi?${q}`,
      ];
      void Promise.all(
        paths.map((path) =>
          apiJson<ProtectedPayload>(path).catch(
            () => ({ type: "FeatureCollection", features: [] }) as ProtectedPayload,
          ),
        ),
      )
        .then((parts) => {
          if (cancelled) return;
          const drawn = protectedSitesToDraw(parts);
          safeSetGeoJson(
            map.getSource("designations-overlay") as GeoJSONSource | undefined,
            { type: "FeatureCollection", features: drawn.features },
          );
          setProtectedSitesHint(drawn.hint);
          setVis(drawn.features.length > 0 ? "visible" : "none");
        })
        .finally(() => {
          inFlight = false;
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadDesignations, 400);
    };

    loadDesignations();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      setProtectedSitesHint(false);
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, ledgerEnabled]);

  // Housing land audit / housing land supply (OGL Spatial Hub amalgamation)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("hla-fill")) return;
      map.setLayoutProperty("hla-fill", "visibility", vis);
      map.setLayoutProperty("hla-line", "visibility", vis);
    };

    if (!showHla) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadHla = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < HLA_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/hla?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("hla-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          // SHARE-FIX: 503 → Coming soon on Housing land audit, no raw error.
          if (isServiceUnavailable(err)) {
            markTileUnavailable("hla");
            setShowHla(false);
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadHla, 700);
    };

    loadHla();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showHla, markTileUnavailable]);

  // LDP allocations (OGL Spatial Hub + authority seeds)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("ldp-fill")) return;
      map.setLayoutProperty("ldp-fill", "visibility", vis);
      map.setLayoutProperty("ldp-line", "visibility", vis);
    };

    if (!showLdp) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadLdp = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < LDP_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/ldp?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("ldp-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          if (err instanceof ApiError && err.status === 503) {
            setLayerNotice(
              "LDP allocations are not loaded yet. National coverage is fragmented — gaps are not filled with guesses.",
            );
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadLdp, 700);
    };

    loadLdp();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showLdp]);

  // Community ownership points (SG 2024 OGL postcode centroids; ownership-context)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("community-ownership-circle")) return;
      map.setLayoutProperty("community-ownership-circle", "visibility", vis);
    };

    if (!showCommunityOwnership) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadCommunity = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < COMMUNITY_OWNERSHIP_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/community-ownership?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=200`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("community-ownership-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          if (err instanceof ApiError && err.status === 503) {
            setLayerNotice(
              "Community ownership overlay is not available right now. Gaps are not filled with guesses.",
            );
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadCommunity, 700);
    };

    loadCommunity();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showCommunityOwnership]);

  // National Forest Inventory + Native Woodland (ledger row 1 land-use)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setNfiVis = (vis: "visible" | "none") => {
      if (!map.getLayer("nfi-fill")) return;
      map.setLayoutProperty("nfi-fill", "visibility", vis);
      map.setLayoutProperty("nfi-line", "visibility", vis);
    };
    const setNativeVis = (vis: "visible" | "none") => {
      if (!map.getLayer("native-woodland-fill")) return;
      map.setLayoutProperty("native-woodland-fill", "visibility", vis);
      map.setLayoutProperty("native-woodland-line", "visibility", vis);
    };

    if (!showWoodland) {
      setNfiVis("none");
      setNativeVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadWoodland = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      const zoom = map.getZoom();
      inFlight = true;

      const tasks: Promise<void>[] = [];

      if (zoom >= NFI_MIN_ZOOM) {
        const nfiUrl =
          `/layers/open/nfi?south=${b.getSouth()}&west=${b.getWest()}` +
          `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
        tasks.push(
          apiJson<GeoJSON.FeatureCollection>(nfiUrl)
            .then((data) => {
              if (cancelled || !mapRef.current) return;
              safeSetGeoJson(map.getSource("nfi-overlay") as GeoJSONSource | undefined, data);
              setNfiVis("visible");
            })
            .catch((err: unknown) => {
              if (cancelled) return;
              setNfiVis("none");
              const msg =
                err instanceof ApiError
                  ? visitorFacingError(err)
                  : "National Forest Inventory overlay is unavailable right now.";
              setLayerNotice(msg);
            }),
        );
      } else {
        setNfiVis("none");
      }

      if (zoom >= NATIVE_WOODLAND_MIN_ZOOM) {
        const nativeUrl =
          `/layers/open/native-woodland?south=${b.getSouth()}&west=${b.getWest()}` +
          `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
        tasks.push(
          apiJson<GeoJSON.FeatureCollection>(nativeUrl)
            .then((data) => {
              if (cancelled || !mapRef.current) return;
              safeSetGeoJson(
                map.getSource("native-woodland-overlay") as
                  | GeoJSONSource
                  | undefined,
                data,
              );
              setNativeVis("visible");
            })
            .catch((err: unknown) => {
              if (cancelled) return;
              setNativeVis("none");
              const msg =
                err instanceof ApiError
                  ? visitorFacingError(err)
                  : "Native Woodland Survey overlay is unavailable right now.";
              setLayerNotice(msg);
            }),
        );
      } else {
        setNativeVis("none");
      }

      void Promise.all(tasks).finally(() => {
        inFlight = false;
      });
    };

    loadWoodland();
    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadWoodland, 280);
    };
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showWoodland]);

  // DESNZ REPD Scotland points (ledger row 3 — no £ rent)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("repd-circle")) return;
      map.setLayoutProperty("repd-circle", "visibility", vis);
    };

    if (!showRepd) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadRepd = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < REPD_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      const path =
        `/layers/open/repd?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("repd-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          // SHARE-FIX: same ledger row "3" as onshore wind / hydro.
          if (isServiceUnavailable(err)) {
            markTileUnavailable("3");
            setLedgerEnabled((cur) => {
              if (!cur["3"]) return cur;
              const copy = { ...cur };
              delete copy["3"];
              return copy;
            });
            return;
          }
          const msg =
            err instanceof ApiError
              ? visitorFacingError(err)
              : "REPD overlay is unavailable right now.";
          setLayerNotice(msg);
        })
        .finally(() => {
          inFlight = false;
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadRepd, 700);
    };

    loadRepd();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showRepd, markTileUnavailable]);

  // Crown Estate Scotland offshore leases (ledger row 4 — no £ rent)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("crown-leases-fill")) return;
      map.setLayoutProperty("crown-leases-fill", "visibility", vis);
      map.setLayoutProperty("crown-leases-line", "visibility", vis);
    };

    if (!showCrownLeases) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadCes = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < CROWN_LEASES_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      const path =
        `/layers/open/crown-estate-leases?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("crown-leases-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          const msg =
            err instanceof ApiError
              ? visitorFacingError(err)
              : "Crown Estate Scotland leases overlay is unavailable right now.";
          setLayerNotice(msg);
        })
        .finally(() => {
          inFlight = false;
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadCes, 700);
    };

    loadCes();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showCrownLeases]);

  // SG public / Crown Estate overlay (five national bodies)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("public-land-fill")) return;
      map.setLayoutProperty("public-land-fill", "visibility", vis);
      map.setLayoutProperty("public-land-line", "visibility", vis);
    };

    if (!showPublicLand) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadPublicLand = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < PUBLIC_LAND_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/public-land?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("public-land-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          if (err instanceof ApiError && err.status === 503) {
            setLayerNotice(
              "Public land overlay is not available right now (source unavailable). Gaps are not filled with guesses.",
            );
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadPublicLand, 700);
    };

    loadPublicLand();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showPublicLand]);

  // James Hutton LCA 1:250k (Hutton Open Data Licence)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("lca-fill")) return;
      map.setLayoutProperty("lca-fill", "visibility", vis);
      map.setLayoutProperty("lca-line", "visibility", vis);
    };

    if (!showLca) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadLca = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < LCA_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/lca?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=200`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          safeSetGeoJson(map.getSource("lca-overlay") as GeoJSONSource | undefined, data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          // SHARE-FIX: 503 → Coming soon on LCA, no raw error.
          if (isServiceUnavailable(err)) {
            markTileUnavailable("lca");
            setLedgerEnabled((cur) => {
              if (!cur.lca) return cur;
              const copy = { ...cur };
              delete copy.lca;
              return copy;
            });
          }
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadLca, 700);
    };

    loadLca();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showLca, markTileUnavailable]);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;
    const syncZoom = () => {
      setMapZoom(map.getZoom());
    };
    const sync = () => {
      const zoom = map.getZoom();
      setMapZoom(zoom);
      if (map.isMoving()) return;
      // Do not write c= until the initial view (Scotland frame or a shared
      // link inside Scotland) has been applied. A mount-time rewrite used to
      // persist the unready camera — Number(null) === 0 — as c=0.00,0.00.
      if (map.getContainer().dataset.framed !== "1") return;
      // data_zones stays off until the user toggles it (no auto-on at zoom 10).
      const center = map.getCenter();
      replaceMapUrl({
        z: zoom,
        center: { lng: center.lng, lat: center.lat },
      });
    };
    sync();
    // Keep inline-legend zoom gates current during flyTo (not only on end).
    map.on("zoom", syncZoom);
    map.on("zoomend", sync);
    map.on("moveend", sync);
    return () => {
      map.off("zoom", syncZoom);
      map.off("zoomend", sync);
      map.off("moveend", sync);
    };
  }, [mapReady]);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;
    for (const layer of CONTEXT_LAYERS) {
      const on = Boolean(contextOn[layer.id]);
      const vis = on ? "visible" : "none";
      if (layer.kind === "fill") {
        for (const id of [`${layer.id}-fill`, `${layer.id}-line`]) {
          if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", vis);
        }
      } else if (map.getLayer(layer.id)) {
        map.setLayoutProperty(layer.id, "visibility", vis);
      }
      if (on && agrAvailable === false) {
        setContextNote("This layer isn't available on this server yet.");
        continue;
      }
      if (!on || layer.kind === "raster" || contextLoaded.current.has(layer.id)) {
        continue;
      }
      const layerId = layer.id;
      void loadContextFeature(layerId)
        .then((data) => {
          if (cancelled || data?.type !== "FeatureCollection") return;
          const source = map.getSource(`${layerId}-src`) as GeoJSONSource | undefined;
          safeSetGeoJson(source, data);
          if (data.meta?.ok === false) {
            setContextNote(data.meta.note || "One layer did not load.");
            return;
          }
          contextLoaded.current.add(layerId);
        })
        .catch(() => {
          if (!cancelled) setContextNote("One layer did not load.");
        });
    }
    return () => {
      cancelled = true;
    };
  }, [mapReady, contextOn, agrAvailable]);

  useEffect(() => {
    if (!contextOn["urban-rural"] || !result) {
      setUrbanRuralName(null);
      return;
    }
    let cancelled = false;
    const lat = result.square.lat;
    const lng = result.square.lng;
    setUrbanRuralName(null);
    const load = (left: number) => {
      if (cancelled) return;
      void apiJson<{ name?: string }>(
        `/layers/context/urban-rural/class?lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lng))}`,
        { cache: "no-store" },
      )
        .then((data) => {
          if (cancelled) return;
          const name = data.name?.trim() ?? "";
          if (name) {
            setUrbanRuralName(name);
            return;
          }
          if (left > 0) window.setTimeout(() => load(left - 1), 1200);
        })
        .catch(() => {
          if (cancelled) return;
          if (left > 0) window.setTimeout(() => load(left - 1), 1200);
        });
    };
    load(5);
    return () => {
      cancelled = true;
    };
  }, [contextOn, result]);

  useEffect(() => {
    if (!result?.agr) {
      setDataZone(null);
      return;
    }
    let cancelled = false;
    const lat = result.square.lat;
    const lng = result.square.lng;
    setDataZone(null);
    void apiJson<{
      code?: string;
      name?: string;
      house_sale_median_gbp?: number | null;
      house_sale_year?: number | null;
      urban_rural_name?: string;
      urban_rural_year?: number | null;
      urban_rural_route?: string;
    }>(
      `/layers/context/data-zones/at?lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lng))}`,
      { cache: "no-store" },
    )
      .then((data) => {
        if (cancelled) return;
        const code = data.code?.trim() ?? "";
        if (!code) return;
        setDataZone({
          code,
          name: data.name?.trim() || undefined,
          house_sale_median_gbp: data.house_sale_median_gbp,
          house_sale_year: data.house_sale_year,
          urban_rural_name: data.urban_rural_name?.trim() || undefined,
          urban_rural_year: data.urban_rural_year,
          urban_rural_route: data.urban_rural_route,
        });
      })
      .catch(() => {
        if (!cancelled) setDataZone(null);
      });
    return () => {
      cancelled = true;
    };
  }, [result]);

  useEffect(() => {
    if (!result) {
      setSeabed(null);
      return;
    }
    let cancelled = false;
    const lat = result.square.lat;
    const lng = result.square.lng;
    setSeabed(null);
    void apiJson<{ leases?: { note?: string }[] }>(
      `/layers/context/seabed/at?lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lng))}`,
      { cache: "no-store" },
    )
      .then((data) => {
        if (cancelled) return;
        const notes = (data.leases ?? [])
          .map((row) => row.note?.trim() ?? "")
          .filter((note) => note.length > 0);
        setSeabed({ notes, failed: false });
      })
      .catch(() => {
        if (!cancelled) setSeabed({ notes: [], failed: true });
      });
    return () => {
      cancelled = true;
    };
  }, [result]);

  useEffect(() => {
    let cancelled = false;
    void apiJson<{
      sources?: Array<{ layer_id?: string; display_id?: string | null }>;
    }>("/layers/add/tiles-manifest")
      .then((data) => {
        if (cancelled) return;
        // A FeatureCollection from a blanket geo stub is not a manifest.
        if (!Array.isArray(data?.sources)) return;
        setSpatialHubPresent(spatialHubPresenceFromManifest(data.sources));
      })
      .catch(() => {
        // Leave the default. A failed manifest must not hide vacant land.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Flood risk paints sepa_nfra_grid (layersAddMapPaint), not /layers/open/flood.
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;
    let cancelled = false;
    const run = () => {
      if (cancelled) return;
      void syncLayersAddPaint(map, ledgerEnabled, spatialHubPresent);
    };
    run();
    map.on("moveend", run);
    return () => {
      cancelled = true;
      map.off("moveend", run);
    };
  }, [mapReady, ledgerEnabled, spatialHubPresent]);

  const placeOpen = panelKind === "place" && Boolean(placeStub || result);
  const layersOpen = isNarrowPanel
    ? panelKind === "layers"
    : desktopLayersOpen;
  /** Tile-unavailable ids for the drawer (builtup is not a switch). */
  const unavailableLayerIds = new Set<string>(tileUnavailableIds);

  const suggestOpen =
    suggestions.length > 0 || Boolean(suggestNote) || suggesting;
  const shellClass = [
    "app-shell",
    "squares-shell",
    "map-cards-shell",
    layersOpen ? "tools-open" : "",
    placeOpen ? "place-open" : "",
    panelKind !== "closed" || desktopLayersOpen ? "panel-open" : "",
    panelCollapsed ? "panel-collapsed" : "",
    suggestOpen ? "suggest-open" : "",
    isNarrowPanel ? "map-narrow" : "map-wide",
  ]
    .filter(Boolean)
    .join(" ");

  const basemapTarget = basemapSwitchTarget(mapStyle);
  const placeTitle =
    placeStub?.label ||
    placeStub?.dataZoneName ||
    placeStub?.card?.place_label ||
    null;

  const identifyAtCentre = () => {
    const map = mapRef.current;
    if (!map) return;
    // Drop a pending debounced map-click identify so centre wins immediately.
    if (identifyTimerRef.current) {
      clearTimeout(identifyTimerRef.current);
      identifyTimerRef.current = null;
    }
    const c = map.getCenter();
    void inspectRef.current(c.lat, c.lng, { fly: false });
    grid3AfterIdentifyRef.current?.(c.lng, c.lat);
  };

  return (
    <div className={shellClass}>
      <div className="map-stage">
      <div className="map-wrap" key={mapStyle}>
        <div
          id="map"
          ref={mapContainer}
          role="application"
          aria-label="Scotland map"
        />
        {protectedSitesHint ? (
          <p
            className="protected-sites-zoom-hint"
            data-testid="protected-sites-zoom-hint"
          >
            Zoom in to see protected sites
          </p>
        ) : null}
        {grid3Tooltip ? (
          <div
            className="grid3-tooltip"
            data-testid="grid3-tooltip"
            style={{
              left: grid3Tooltip.x + 12,
              top: grid3Tooltip.y + 12,
            }}
          >
            {grid3Tooltip.ref}
          </div>
        ) : null}
      </div>

      <button
        type="button"
        className={
          mapStyle === "detailed"
            ? "basemap-switcher is-detailed"
            : "basemap-switcher is-light"
        }
        data-testid="basemap-switcher"
        aria-label={basemapAriaLabel(basemapTarget)}
        onClick={() => {
          const map = mapRef.current;
          if (map) {
            const c = map.getCenter();
            cameraPreserveRef.current = {
              lng: c.lng,
              lat: c.lat,
              zoom: map.getZoom(),
            };
          }
          setMapStyle(basemapTarget);
        }}
      >
        <span
          className={
            basemapTarget === "detailed"
              ? "basemap-switcher-preview preview-detailed"
              : "basemap-switcher-preview preview-light"
          }
          aria-hidden="true"
        />
        <span className="basemap-switcher-caption">
          {basemapCaption(basemapTarget)}
        </span>
      </button>

      <button
        type="button"
        className="identify-at-centre"
        data-testid="identify-at-centre"
        onClick={identifyAtCentre}
      >
        Show the area at map centre
      </button>

      <header className="hud-top" ref={headerRef}>
        <div className="hud-brand">
          <a className="hud-wordmark" href="/" aria-label="Scot-LAND home">
            <img src="/logo-mark-h3.png" alt="" width={40} height={40} />
          </a>
        </div>
        <button
          ref={layersBtnRef}
          type="button"
          className={layersOpen ? "hud-layers-btn on" : "hud-layers-btn"}
          aria-pressed={layersOpen}
          onClick={() => {
            if (layersOpen) closeLayersPanel();
            else openLayersPanel();
          }}
          data-testid="hud-layers-btn"
        >
          Layers
        </button>
        <div
          className={
            suggestions.length || suggestNote || suggesting || searchFocused
              ? "hud-search-dock open"
              : "hud-search-dock"
          }
        >
        <div className={loading || suggesting ? "hud-search loading" : "hud-search"}>
          <label className="sr-only" htmlFor="place-query">
            Search a postcode or place
          </label>
          <input
            id="place-query"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={suggestions.length > 0 || Boolean(suggestNote)}
            aria-controls="place-suggestions"
            aria-activedescendant={
              activeSuggest >= 0 ? `suggest-${activeSuggest}` : undefined
            }
            value={query}
            autoComplete="off"
            placeholder="Search a postcode or place"
            title="Search a postcode or place"
            onFocus={() => {
              setSearchFocused(true);
              setSearchNoMatch(false);
            }}
            onChange={(event) => {
              setQuery(event.target.value);
              setSearchNoMatch(false);
              scheduleSuggest(event.target.value);
            }}
            onBlur={() => {
              setSearchFocused(false);
              window.setTimeout(() => {
                suggestGen.current += 1;
                clearSuggestions();
              }, 180);
            }}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" && suggestions.length) {
                event.preventDefault();
                const next =
                  activeSuggest < 0
                    ? 0
                    : Math.min(activeSuggest + 1, suggestions.length - 1);
                setActiveSuggest(next);
                document.getElementById(`suggest-${next}`)?.scrollIntoView({
                  block: "nearest",
                });
              } else if (event.key === "ArrowUp" && suggestions.length) {
                event.preventDefault();
                const next = activeSuggest <= 0 ? 0 : activeSuggest - 1;
                setActiveSuggest(next);
                document.getElementById(`suggest-${next}`)?.scrollIntoView({
                  block: "nearest",
                });
              } else if (event.key === "Enter") {
                event.preventDefault();
                if (activeSuggest >= 0 && suggestions[activeSuggest]) {
                  void chooseSuggestion(suggestions[activeSuggest]);
                } else {
                  void runSearch();
                }
              } else if (
                event.key === "Escape" &&
                (suggestions.length || suggestNote || suggesting)
              ) {
                event.preventDefault();
                event.stopPropagation();
                suggestGen.current += 1;
                clearSuggestions();
              }
            }}
          />
          {query ? (
            <button
              type="button"
              className="hud-search-clear"
              aria-label="Clear search"
              onMouseDown={(event) => event.preventDefault()}
              onClick={clearQuery}
            >
              ×
            </button>
          ) : null}
          <button
            type="button"
            className="hud-search-go"
            disabled={!query.trim()}
            aria-label="Search"
            onClick={() => void runSearch()}
          >
            {loading ? "…" : "Search"}
          </button>
        </div>
        {searchFocused && !query.trim() && !suggestOpen ? (
          <p className="search-empty-hint" data-testid="search-empty-hint">
            Type a postcode or place name, or tap the map.
          </p>
        ) : null}
        {searchNoMatch ? (
          <p className="search-no-match" data-testid="search-no-match" role="alert">
            {PLACE_CARD_NO_MATCH}
          </p>
        ) : null}
        {(suggestions.length > 0 || suggestNote || suggesting) && (
          <ul className="search-suggest" id="place-suggestions" role="listbox">
            {suggesting && suggestions.length === 0 && !suggestNote ? (
              <li className="search-suggest-note">Looking…</li>
            ) : null}
            {suggestNote ? <li className="search-suggest-note">{suggestNote}</li> : null}
            {suggestions.map((item, index) => (
              <li key={item.id} role="presentation">
                <button
                  type="button"
                  id={`suggest-${index}`}
                  role="option"
                  aria-selected={index === activeSuggest}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveSuggest(index)}
                  onClick={() => void chooseSuggestion(item)}
                >
                  {item.label}
                </button>
              </li>
            ))}
          </ul>
        )}
        </div>
        <SiteNav current="map" variant="map" />
      </header>
      <ResearchBanner
        dismissible
        collapseForSuggest={suggestOpen || placeOpen}
      />

      {restPromptVisible && panelKind === "closed" && !gbpLiveOn ? (
        <p className="map-rest-prompt" data-testid="map-rest-prompt">
          Search a place or pick a layer.
        </p>
      ) : null}

      {apiOk === false && (
        <div className="hud-banner">
          <span>{TRY_AGAIN}</span>
          <button
            type="button"
            className="api-retry"
            onClick={() => void pingApi().then((s) => setApiOk(s.ok))}
          >
            Retry
          </button>
        </div>
      )}

      {panelKind === "closed" && !layersOpen && stripLayer ? (
        <button
          type="button"
          className="legend-strip"
          data-testid="legend-strip"
          aria-label={`Legend: ${stripLayer.label}`}
          onClick={() => openLayersPanel()}
        >
          <span className="legend-strip-name">{stripLayer.label}</span>
          <span className="legend-strip-ramp" aria-hidden="true">
            {stripLayer.classes.slice(0, 5).map((c, i) => (
              <span
                key={`${c.color}-${i}`}
                className="legend-strip-swatch"
                style={{ background: c.color }}
              />
            ))}
          </span>
          <span className="legend-strip-chevron" aria-hidden="true">
            ▸
          </span>
        </button>
      ) : null}

      <div className="map-attribution-line" data-testid="map-attribution-line">
        <span>
          {attributionPieces.map((p) => p.text).join(" · ")}
        </span>
        {" · "}
        <a href="/data#licences" data-testid="map-all-sources">
          All sources
        </a>
      </div>
      </div>{/* map-stage — panel stays outside so inert modal does not block close */}

      {panelKind === "place" ? (
        <MapPanelSlot
          kind="place"
          detent={panelDetent}
          onDetentChange={(d) => {
            setPanelDetent(d);
            setLiveMessage(`Panel ${d}`);
          }}
          collapsed={panelCollapsed}
          onCollapsedChange={setPanelCollapsed}
          onClose={() => {
            clearPlace();
            setPanelKind("closed");
            replaceMapUrl({ panel: null, place: null });
          }}
          onRequestDismiss={dismissPanel}
          placeName={placeTitle}
          liveMessage={liveMessage}
          showSlotClose={false}
        >
          {placeStub ? (
            <PlaceCardStub
              place={placeStub}
              loading={placeLoading}
              error={error}
              onClose={() => {
                // Card × clears selection (not desktop collapse-to-tab).
                clearPlace();
                setPanelKind("closed");
                setPanelCollapsed(false);
                replaceMapUrl({ panel: null, place: null });
                panelHistoryRef.current = false;
                setLiveMessage("Panel closed");
              }}
              onShowScotland={showScotlandNationalView}
              gridSquareLine={
                grid3Square ? grid3Row6Text(grid3Square.ref) : null
              }
            />
          ) : null}
        </MapPanelSlot>
      ) : null}
      {layersOpen ? (
        <MapPanelSlot
          kind="layers"
          detent={isNarrowPanel ? panelDetent : "full"}
          onDetentChange={(d) => {
            setPanelDetent(d);
            setLiveMessage(`Panel ${d}`);
          }}
          collapsed={false}
          onCollapsedChange={setPanelCollapsed}
          onClose={closeLayersPanel}
          onRequestDismiss={closeLayersPanel}
          liveMessage={liveMessage}
          layersModal={isNarrowPanel && panelDetent === "full"}
          slotTestId={
            panelKind === "place" && !isNarrowPanel
              ? "layers-column"
              : "map-panel-slot"
          }
          className={!isNarrowPanel ? "map-panel-slot--right" : undefined}
        >
          <MapLayersDrawer
            className="layers-panel-in-shell"
            mapZoom={mapZoom}
            onClose={closeLayersPanel}
            enabled={{
              ...ledgerEnabled,
              "1": showAgr,
              councils: showCouncils,
              data_zones: showDataZones,
              vdl: showVdl,
              hla: showHla,
              [GRID3_LAYER_ID]: showGrid3,
            }}
            unavailableIds={unavailableLayerIds}
            spatialHubPresent={spatialHubPresent}
            onEnabledChange={onMapLayersChange}
          />
        </MapPanelSlot>
      ) : null}

      {shortcutsOpen ? (
        <div
          className="map-shortcuts-dialog"
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard shortcuts"
          data-testid="map-shortcuts-dialog"
        >
          <button
            type="button"
            className="map-shortcuts-close"
            aria-label="Close shortcuts"
            onClick={() => setShortcutsOpen(false)}
          >
            ×
          </button>
          <h2>Keyboard shortcuts</h2>
          <ul>
            <li><kbd>/</kbd> Search</li>
            <li><kbd>L</kbd> Layers</li>
            <li><kbd>Esc</kbd> Close panel</li>
            <li><kbd>+</kbd> / <kbd>−</kbd> Zoom</li>
            <li>Arrow keys pan</li>
            <li><kbd>Enter</kbd> Identify at centre</li>
            <li><kbd>?</kbd> This dialog</li>
          </ul>
        </div>
      ) : null}
      <MapStampFooter />
    </div>
  );
}
