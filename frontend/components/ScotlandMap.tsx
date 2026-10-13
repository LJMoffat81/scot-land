"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl, {
  Map,
  GeoJSONSource,
  ExpressionSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  MapStampFooter,
  type AgrResult,
  type PlaceFiscal,
  type ScenarioId,
} from "./AgrBreakdown";
import PlaceCardStub, { type PlaceStub } from "./PlaceCardStub";
import LedgerPanel from "./LedgerPanel";
import {
  ApiError,
  SERVICE_BUSY,
  apiFetch,
  apiJson,
  isServiceFailure,
  pingApi,
  fetchCapabilities,
  POSTCODES_ONLY,
  looksLikeFullPostcode,
  parseCoordinates,
  visitorFacingError,
} from "../lib/api";
import { CONTEXT_LAYERS } from "../lib/contextLayers";
import type { LedgerToggleState } from "../lib/ledger";

type ParcelFeature = GeoJSON.Feature<
  GeoJSON.Polygon | GeoJSON.MultiPolygon,
  {
    label?: string;
    area_sqm?: number;
    inspire_id?: string;
    national_reference?: string;
  }
>;

type SquareResponse = {
  square: {
    lat: number;
    lng: number;
    area_sqm: number;
    polygon: GeoJSON.Polygon;
    grid?: string;
  };
  reason?: string;
  agr: AgrResult | null;
  what3words?: string | null;
  w3w_configured?: boolean;
  sales_context?: import("./AgrBreakdown").SalesContext | null;
  parcel?: ParcelFeature | null;
  fiscal?: PlaceFiscal | null;
  postcode?: {
    postcode: string;
    admin_district: string | null;
    country: string | null;
  };
  platform?: import("./AgrBreakdown").PlatformContext | null;
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

type MetricId =
  | "agr_plot"
  | "rent_per_sqm"
  | "house_price"
  | "agr_price_pct"
  | "land_share"
  | "site_capital"
  | "simd"
  | "pop_density"
  | "net_contribution"
  | "gross_liability"
  | "vacant_residual";

type MetricDef = {
  id: MetricId;
  property: string;
  label: string;
  group: "value" | "context" | "fiscal";
  stops: [number, string][];
};

const emptyCollection: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

/** Colour ramps tuned to each metric’s typical Scotland range. */
const METRICS: MetricDef[] = [
  {
    id: "agr_plot",
    property: "annual_ground_rent_plot_gbp",
    label: "Typical plot rent",
    group: "value",
    stops: [
      [0, "#ffffcc"],
      [500, "#c7e9b4"],
      [1500, "#7fcdbb"],
      [3000, "#41b6c4"],
      [4500, "#2c7fb8"],
      [6500, "#253494"],
    ],
  },
  {
    id: "rent_per_sqm",
    property: "site_rental_per_sqm_gbp",
    label: "Rent per square metre",
    group: "value",
    stops: [
      [0, "#f7fcf5"],
      [5, "#c7e9c0"],
      [12, "#74c476"],
      [20, "#31a354"],
      [30, "#006d2c"],
    ],
  },
  {
    id: "house_price",
    property: "average_price_gbp",
    label: "House prices",
    group: "value",
    stops: [
      [100000, "#fff5f0"],
      [140000, "#fcbba1"],
      [180000, "#fc9272"],
      [220000, "#ef3b2c"],
      [280000, "#a50f15"],
    ],
  },
  {
    id: "agr_price_pct",
    property: "agr_as_pct_of_price",
    label: "Rent as a share of price",
    group: "value",
    stops: [
      [0.5, "#f7fbff"],
      [1.5, "#c6dbef"],
      [2.5, "#6baed6"],
      [3.5, "#2171b5"],
      [5, "#08306b"],
    ],
  },
  {
    id: "land_share",
    property: "site_share_pct",
    label: "Land share %",
    group: "value",
    stops: [
      [30, "#f7fcfd"],
      [45, "#ccece6"],
      [55, "#66c2a4"],
      [65, "#238b45"],
      [75, "#00441b"],
    ],
  },
  {
    id: "site_capital",
    property: "site_capital_per_sqm_gbp",
    label: "Land value per square metre",
    group: "value",
    stops: [
      [50, "#fcfbfd"],
      [150, "#dadaeb"],
      [300, "#9e9ac8"],
      [450, "#6a51a3"],
      [600, "#3f007d"],
    ],
  },
  {
    id: "simd",
    property: "simd_pct_20most_deprived",
    label: "Deprivation",
    group: "context",
    stops: [
      [0, "#ffffd4"],
      [8, "#fed98e"],
      [16, "#fe9929"],
      [28, "#d95f0e"],
      [40, "#993404"],
    ],
  },
  {
    id: "pop_density",
    property: "population_density_per_km2",
    label: "People per square kilometre",
    group: "context",
    stops: [
      [10, "#f7fcf0"],
      [100, "#ccebc5"],
      [500, "#7bccc4"],
      [1500, "#2b8cbe"],
      [3000, "#084081"],
    ],
  },
  {
    id: "gross_liability",
    property: "gross_plot_liability_gbp",
    label: "Annual Ground Rent",
    group: "fiscal",
    stops: [
      [0, "#ffffcc"],
      [1500, "#c7e9b4"],
      [3500, "#41b6c4"],
      [5500, "#2c7fb8"],
      [8000, "#253494"],
    ],
  },
  {
    id: "net_contribution",
    property: "net_contribution_plot_gbp",
    label: "Against one person's share",
    group: "fiscal",
    // Teal is below one person's share. Orange is above it.
    stops: [
      [-18000, "#01665e"],
      [-5000, "#80cdc1"],
      [0, "#f5f5f5"],
      [2000, "#fdb863"],
      [6000, "#b35806"],
    ],
  },
  {
    id: "vacant_residual",
    property: "vacant_full_agr_gbp",
    label: "Vacant land",
    group: "context",
    stops: [
      [0, "#fff5eb"],
      [2_000_000, "#fdd0a2"],
      [8_000_000, "#fd8d3c"],
      [20_000_000, "#e6550d"],
      [40_000_000, "#a63603"],
    ],
  },
];

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
const VDL_MIN_ZOOM = 8;
/** Data Zone outlines are readable from neighbourhood zoom. */
const DATA_ZONE_MIN_ZOOM = 10;

const VDL_SITE_TYPES: Array<{ name: string; color: string }> = [
  { name: "Vacant Land", color: "#e8a317" },
  { name: "Vacant Land and Buildings", color: "#c45c26" },
  { name: "Derelict", color: "#7a2e00" },
];

const VDL_FILL: ExpressionSpecification = [
  "match",
  ["coalesce", ["get", "site_type"], ""],
  "Vacant Land",
  "#e8a317",
  "Vacant Land and Buildings",
  "#c45c26",
  "Derelict",
  "#7a2e00",
  "#c45c26",
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
  vdlName?: string | null;
  vdlSiteType?: string | null;
  vdlSizeHa?: number | null;
  vdlSiteCode?: string | null;
  vdlOwnerClass?: string | null;
  vdlGeometrySource?: string | null;
  source?: string | null;
}): string | null {
  const rows: string[] = [];
  if (parts.parcelId) {
    rows.push(
      `<strong>Cadastral parcel</strong><br/>ID: ${escapeHtml(parts.parcelId)}`,
    );
  }
  if (parts.areaSqm != null && Number.isFinite(parts.areaSqm)) {
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
  if (
    parts.vdlName ||
    parts.vdlSiteType ||
    parts.vdlSiteCode ||
    parts.vdlSizeHa != null
  ) {
    const title = parts.vdlName
      ? escapeHtml(parts.vdlName)
      : "Vacant / derelict site";
    rows.push(`<strong>SVDLS</strong><br/>${title}`);
    if (parts.vdlSiteType) {
      rows.push(`Type: ${escapeHtml(parts.vdlSiteType)}`);
    }
    if (parts.vdlSiteCode) {
      rows.push(`Site code: ${escapeHtml(parts.vdlSiteCode)}`);
    }
    if (parts.vdlSizeHa != null && Number.isFinite(parts.vdlSizeHa)) {
      rows.push(`Size: ${parts.vdlSizeHa.toLocaleString("en-GB")} ha`);
    }
    if (parts.vdlOwnerClass) {
      rows.push(
        `Owner class (survey): ${escapeHtml(parts.vdlOwnerClass)}`,
      );
    }
    if (parts.vdlGeometrySource) {
      rows.push(
        `Geometry: ${escapeHtml(parts.vdlGeometrySource)}`,
      );
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
  const stops = metric.stops.flatMap(([v, c]) => [v, c]);
  return [
    "interpolate",
    ["linear"],
    ["coalesce", ["get", metric.property], 0],
    ...stops,
  ] as ExpressionSpecification;
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
  const [addressLine, setAddressLine] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>("full_agr");
  // Public shell: never paint council-area AGR £ / rent £/m² (internal-only until calibration).
  const choropleth: MetricId | "off" = "off";
  const [showBoundaries, setShowBoundaries] = useState(false);
  const [showCellGrid] = useState(false);
  const [showVdl, setShowVdl] = useState(false);
  // SG 2024 public/Crown dashboard: licence unverified/not open — never paint
  const showPublicLand = false;
  const [showDataZones, setShowDataZones] = useState(false);
  /** Ledger row + constraint toggles (paint where the rent class / constraint applies). */
  const [ledgerEnabled, setLedgerEnabled] = useState<LedgerToggleState>({});
  const [layerNotice, setLayerNotice] = useState<string | null>(null);
  const dataZonesTouched = useRef(false);
  const boundariesTouched = useRef(false);
  const layerPopupRef = useRef<maplibregl.Popup | null>(null);
  const dzHoverPopupRef = useRef<maplibregl.Popup | null>(null);

  const onLedgerEnabledChange = (next: LedgerToggleState) => {
    setLedgerEnabled(next);
    // Constraint flood paints the existing flood context overlay when available.
    setContextOn((cur) => ({ ...cur, flood: Boolean(next.flood) }));
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
  const contextFlight = useRef<Set<string>>(new Set());
  const [, setLayerBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SquareResponse | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  // Legacy ground-rent router mounted? null = not known yet. Its endpoints are never called when false.
  const [agrAvailable, setAgrAvailable] = useState<boolean | null>(null);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [mapStyle, setMapStyle] = useState<"streets" | "satellite">("streets");
  const [legendOpen, setLegendOpen] = useState(false);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const parcelLabelRef = useRef<maplibregl.Marker | null>(null);
  const headerRef = useRef<HTMLElement | null>(null);
  const scotlandRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const header = headerRef.current;
    const scotland = scotlandRef.current;
    const apply = () => {
      const shell = header?.parentElement ?? scotland?.parentElement;
      if (!shell) return;
      if (header) shell.style.setProperty("--hud-height", `${header.offsetHeight}px`);
      if (scotland) {
        shell.style.setProperty("--scotland-height", `${scotland.offsetHeight}px`);
      }
    };
    apply();
    const observer = new ResizeObserver(apply);
    if (header) observer.observe(header);
    if (scotland) observer.observe(scotland);
    return () => observer.disconnect();
  }, []);

  const applyResult = useCallback((payload: SquareResponse) => {
    setResult(payload);
    if (payload.agr?.active_scenario) {
      setScenario(payload.agr.active_scenario);
    }
    // One shot per new result. Do not tie this to later renders, or Show legend cannot reopen it.
    if (window.matchMedia("(max-width: 640px)").matches) {
      setLegendOpen(false);
    }

    const map = mapRef.current;
    if (map) {
      markerRef.current?.remove();
      markerRef.current = new maplibregl.Marker({ color: "#0076d3" })
        .setLngLat([payload.square.lng, payload.square.lat])
        .addTo(map);
      // Public shell: never label parcels with modelled AGR £ / year.
      parcelLabelRef.current?.remove();
      parcelLabelRef.current = null;
    }
    if (map?.getSource("selected-square")) {
      const source = map.getSource("selected-square") as GeoJSONSource;
      source.setData({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            geometry: payload.square.polygon,
            properties: {},
          },
        ],
      });
    }

    if (map?.getSource("selected-parcel")) {
      const parcelSrc = map.getSource("selected-parcel") as GeoJSONSource;
      if (payload.parcel?.geometry) {
        parcelSrc.setData({
          type: "FeatureCollection",
          features: [payload.parcel],
        });
      } else {
        parcelSrc.setData(emptyCollection);
      }
    }

    if (payload.what3words) {
      setQuery(`///${payload.what3words.replace(/^\/+/, "")}`);
    }

    if (map) {
      const z = map.getZoom();
      const targetZoom = payload.parcel
        ? Math.max(z < 6.5 ? 16 : z, 16)
        : z < 6.5
          ? 7
          : Math.min(Math.max(z, 15), 18);
      if (targetZoom >= 14 && !boundariesTouched.current) setShowBoundaries(true);
      map.flyTo({
        center: [payload.square.lng, payload.square.lat],
        zoom: Math.min(targetZoom, 18),
        essential: true,
      });
    }

    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("lat", payload.square.lat.toFixed(6));
      url.searchParams.set("lng", payload.square.lng.toFixed(6));
      if (payload.what3words) {
        url.searchParams.set("words", payload.what3words);
      } else {
        url.searchParams.delete("words");
      }
      window.history.replaceState({}, "", url.toString());
    }
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
    setResult(null);
    setError(null);
    setAddressLine(null);
    setPlaceStub(null);
    setPlaceLoading(false);
    markerRef.current?.remove();
    markerRef.current = null;
    parcelLabelRef.current?.remove();
    parcelLabelRef.current = null;
    const map = mapRef.current;
    if (map?.getSource("selected-square")) {
      (map.getSource("selected-square") as GeoJSONSource).setData(
        emptyCollection,
      );
    }
    if (map?.getSource("selected-parcel")) {
      (map.getSource("selected-parcel") as GeoJSONSource).setData(
        emptyCollection,
      );
    }
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("lat");
      url.searchParams.delete("lng");
      url.searchParams.delete("words");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  // Public path for a point (map click, Locate, search, ?lat=&lng=): marker, optional fly,
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
      } = {},
    ) => {
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      const gen = ++lookupGen.current;
      const map = mapRef.current;
      markerRef.current?.remove();
      if (map) {
        markerRef.current = new maplibregl.Marker({ color: "#0076d3" })
          .setLngLat([lng, lat])
          .addTo(map);
        if (opts.fly) {
          map.flyTo({
            center: [lng, lat],
            zoom: Math.max(map.getZoom(), 15),
            essential: true,
          });
        }
      }
      if (typeof window !== "undefined") {
        const url = new URL(window.location.href);
        url.searchParams.set("lat", lat.toFixed(6));
        url.searchParams.set("lng", lng.toFixed(6));
        url.searchParams.delete("words");
        window.history.replaceState({}, "", url.toString());
      }
      setError(null);
      setResult(null);
      setAddressLine(opts.label ?? null);
      const knownCode = opts.dataZoneCode?.trim() || null;
      const knownName = opts.dataZoneName?.trim() || null;
      setPlaceStub({
        lat,
        lng,
        label: opts.label ?? knownName ?? null,
        postcode: opts.postcode ?? null,
        dataZoneCode: knownCode,
        dataZoneName: knownName,
        dataZoneVintage: opts.dataZoneVintage ?? null,
        laName: opts.laName ?? null,
        population: opts.population ?? null,
        popYear: opts.popYear ?? null,
        dwellings: opts.dwellings ?? null,
        dwYear: opts.dwYear ?? null,
      });
      if (window.matchMedia("(max-width: 640px)").matches) {
        setLegendOpen(false);
      }
      // Polygon click already supplies code/name (+ optional rollups).
      if (knownCode) {
        setPlaceLoading(false);
        return;
      }
      setPlaceLoading(true);
      try {
        const data = await apiJson<{
          code?: string;
          name?: string;
          vintage?: number;
        }>(
          `/layers/context/data-zones/at?lat=${encodeURIComponent(String(lat))}&lng=${encodeURIComponent(String(lng))}`,
          { cache: "no-store" },
        );
        if (gen !== lookupGen.current) return;
        const code = data.code?.trim() || null;
        const name = data.name?.trim() || null;
        setPlaceStub((prev) =>
          prev && prev.lat === lat && prev.lng === lng
            ? {
                ...prev,
                dataZoneCode: code,
                dataZoneName: name,
                dataZoneVintage:
                  typeof data.vintage === "number" ? data.vintage : null,
              }
            : prev,
        );
      } catch {
        /* zone label is best-effort; card still shows coordinates */
      } finally {
        if (gen === lookupGen.current) setPlaceLoading(false);
      }
    },
    [],
  );
  const inspectRef = useRef(selectPlace);
  inspectRef.current = selectPlace;

  const locateMe = useCallback(() => {
    if (!navigator.geolocation) {
      setError("This browser cannot share a location.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        setLoading(false);
        setError(null);
        void inspectRef.current(latitude, longitude, { fly: true });
      },
      () => {
        setLoading(false);
        setError(
          "Location unavailable. Allow location access, or search a postcode.",
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    );
  }, []);

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
      if (event.key !== "Escape") return;
      if (toolsOpen) {
        setToolsOpen(false);
        return;
      }
      if (placeStub || result || error) clearPlace();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toolsOpen, placeStub, result, error, clearPlace]);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("satellite")) return;
    map.setLayoutProperty(
      "satellite",
      "visibility",
      mapStyle === "satellite" ? "visible" : "none",
    );
  }, [mapReady, mapStyle]);

  const openPostcode = async (postcode: string, generation: number) => {
    const response = await apiFetch(
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
    });
  };

  const openWords = async (words: string, generation: number) => {
    // Public shell: resolve ///words via /place only (no /square AGR £).
    const response = await apiFetch(
      `/place?q=${encodeURIComponent(`///${words.replace(/^\/+/, "")}`)}`,
    );
    const body = (await response.json()) as PlaceLookup;
    if (generation !== lookupGen.current) return;
    if (body.kind === "point" && body.lat != null && body.lng != null) {
      await inspectRef.current(body.lat, body.lng, {
        fly: true,
        label: body.label ?? `///${words}`,
      });
      return;
    }
    if (body.kind === "words" && body.lat != null && body.lng != null) {
      await inspectRef.current(body.lat, body.lng, {
        fly: true,
        label: `///${body.words ?? words}`,
      });
      return;
    }
    setError(body.note || "Those three words did not resolve on the map.");
  };

  const clearSuggestions = () => {
    setSuggestions([]);
    setSuggestNote(null);
    setActiveSuggest(-1);
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
      );
      if (generation !== lookupGen.current) return;
      setQuery(body.postcode);
      void inspectRef.current(body.lat, body.lng, { fly: true });
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
      const response = await apiFetch(`/place?q=${encodeURIComponent(q)}`);
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
        });
      } else {
        clearPlace();
        setError(
          body.note ||
            "No place matched. Try a postcode, place name, coordinates, or click the map.",
        );
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
      if (generation === lookupGen.current) setLoading(false);
    }
  };

  const chooseSuggestion = async (item: Suggestion) => {
    const generation = ++lookupGen.current;
    suggestGen.current += 1;
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    clearSuggestions();
    setQuery(item.label);
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
      if (generation === lookupGen.current) setLoading(false);
    }
  };

  const loadSuggestions = async (text: string) => {
    const generation = ++suggestGen.current;
    if (!(await fetchCapabilities()).agr) {
      setSuggestions([]);
      setSuggestNote(
        looksLikeFullPostcode(text) ? "Press Enter to find this postcode." : POSTCODES_ONLY,
      );
      return;
    }
    setSuggesting(true);
    try {
      const response = await apiFetch(`/place?q=${encodeURIComponent(text)}`);
      const body = (await response.json()) as PlaceLookup;
      if (generation !== suggestGen.current) return;
      const found = suggestionsFromLookup(body, text);
      setSuggestions(found.items);
      setSuggestNote(found.items.length ? null : found.note);
      setActiveSuggest(found.items.length ? 0 : -1);
    } catch (err) {
      if (generation !== suggestGen.current) return;
      setSuggestions([]);
      setActiveSuggest(-1);
      if (!isServiceFailure(err)) setSuggestNote(visitorFacingError(err));
      else setSuggestNote(null);
    } finally {
      if (generation === suggestGen.current) setSuggesting(false);
    }
  };

  const scheduleSuggest = (value: string) => {
    if (suggestTimer.current) clearTimeout(suggestTimer.current);
    const text = value.trim();
    if (text.length < 3) {
      suggestGen.current += 1;
      clearSuggestions();
      setSuggesting(false);
      return;
    }
    suggestTimer.current = setTimeout(() => {
      void loadSuggestions(text);
    }, 450);
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

    const map = new maplibregl.Map({
      container,
      // CARTO's raster tiles now stamp "API key required" unless a key is set.
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [-4.2, 57.5],
      zoom: 5.7,
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.getCanvas().style.cursor = "pointer";

    let userMoved = false;
    const noteUserMove = (event: { originalEvent?: Event }) => {
      if (event.originalEvent) userMoved = true;
    };
    map.on("dragstart", noteUserMove);
    map.on("zoomstart", noteUserMove);
    const frameScotland = () => {
      if (userMoved) return;
      if (container.clientWidth < 40 || container.clientHeight < 40) return;
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
      const center = map.getCenter();
      container.dataset.lng = center.lng.toFixed(5);
      container.dataset.lat = center.lat.toFixed(5);
      container.dataset.zoom = map.getZoom().toFixed(3);
      container.dataset.framed = "1";
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
      map.addSource("council-metrics", { type: "geojson", data: emptyCollection });
      map.addLayer({
        id: "council-fill",
        type: "fill",
        source: "council-metrics",
        paint: {
          "fill-color": paintForMetric(METRICS[0]),
          "fill-opacity": 0.72,
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

      map.addSource("w3w-agr-grid", { type: "geojson", data: emptyCollection });
      map.addLayer({
        id: "w3w-agr-fill",
        type: "fill",
        source: "w3w-agr-grid",
        layout: { visibility: "none" },
        paint: {
          "fill-color": CELL_AGR_COLOR,
          "fill-opacity": 0.7,
        },
      });
      map.addLayer({
        id: "w3w-agr-line",
        type: "line",
        source: "w3w-agr-grid",
        layout: { visibility: "none" },
        paint: { "line-color": "#7f0000", "line-width": 0.4, "line-opacity": 0.4 },
      });

      map.addSource("data-zones-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Scottish Government Data Zone boundaries 2011 (OGL). Outlines only — not a rent.",
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

      map.addSource("vdl-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "SVDLS © Scottish Government / Improvement Service (OGL v3.0). Survey sites, not a title.",
      });
      map.addLayer({
        id: "vdl-fill",
        type: "fill",
        source: "vdl-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": VDL_FILL,
          "fill-opacity": 0.42,
        },
      });
      map.addLayer({
        id: "vdl-line",
        type: "line",
        source: "vdl-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#5a2200", "line-width": 1.1, "line-opacity": 0.9 },
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

      map.addSource("parcels-wms", {
        type: "raster",
        tiles: ["/api/parcels/tiles/{z}/{x}/{y}"],
        tileSize: 256,
        minzoom: 14,
        maxzoom: 19,
        scheme: "xyz",
        attribution:
          "© Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data. © Crown copyright and database right 2026. OGL-3.0.",
      });
      map.addLayer({
        id: "parcels-wms",
        type: "raster",
        source: "parcels-wms",
        minzoom: 14,
        paint: { "raster-opacity": 0.9, "raster-fade-duration": 0 },
        layout: { visibility: "none" },
      });

      // PostGIS Index Polygons bbox (same contract as public-land / VDL).
      // When unloaded (503), stay empty and rely on live WMS tiles above.
      map.addSource("parcels-postgis", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "RoS INSPIRE Index Polygons (OGL-3.0). Registered extents only — not a title.",
      });
      map.addLayer({
        id: "parcels-postgis-fill",
        type: "fill",
        source: "parcels-postgis",
        minzoom: CADASTRAL_MIN_ZOOM,
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#5c4a1f",
          "fill-opacity": 0.08,
        },
      });
      map.addLayer({
        id: "parcels-postgis-line",
        type: "line",
        source: "parcels-postgis",
        minzoom: CADASTRAL_MIN_ZOOM,
        layout: { visibility: "none" },
        paint: {
          "line-color": "#5c4a1f",
          "line-width": 1.1,
          "line-opacity": 0.85,
        },
      });

      map.addSource("selected-parcel", { type: "geojson", data: emptyCollection });
      map.addLayer({
        id: "selected-parcel-fill",
        type: "fill",
        source: "selected-parcel",
        paint: { "fill-color": "#0b1e3a", "fill-opacity": 0.12 },
      });
      map.addLayer({
        id: "selected-parcel-outline",
        type: "line",
        source: "selected-parcel",
        paint: { "line-color": "#0b1e3a", "line-width": 2.25, "line-opacity": 0.95 },
      });

      map.addSource("selected-square", { type: "geojson", data: emptyCollection });
      map.addLayer({
        id: "selected-square-fill",
        type: "fill",
        source: "selected-square",
        paint: { "fill-color": "#0076d3", "fill-opacity": 0.18 },
      });
      map.addLayer({
        id: "selected-square-outline",
        type: "line",
        source: "selected-square",
        paint: { "line-color": "#0076d3", "line-width": 2.75 },
      });

      map.addSource("satellite", {
        type: "raster",
        tiles: [
          "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        ],
        tileSize: 256,
        attribution: "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community",
      });
      map.addLayer(
        {
          id: "satellite",
          type: "raster",
          source: "satellite",
          layout: { visibility: "none" },
        },
        "council-fill",
      );

      setMapReady(true);

      const params = new URLSearchParams(window.location.search);
      const qWords = params.get("words");
      const qLat = params.get("lat");
      const qLng = params.get("lng");
      // public/Crown 2024 dashboard: licence unverified/not open — never paint
      // Council AGR £ / rent £/m² / band choropleth: scrubbed from public shell
      if (params.get("vacant") === "1") {
        setShowVdl(true);
      }
      if (qWords) {
        setQuery(qWords);
        void (async () => {
          if (!(await fetchCapabilities()).agr) return;
          const generation = ++lookupGen.current;
          try {
            await openWords(qWords, generation);
            setApiOk(true);
          } catch (err) {
            setError(visitorFacingError(err));
            if (isServiceFailure(err)) {
              void pingApi().then((s) => setApiOk(s.ok));
            }
          }
        })();
      } else if (qLat && qLng) {
        void inspectRef.current(Number(qLat), Number(qLng), { fly: true });
      }
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

    map.on("click", async (event) => {
      const lat = event.lngLat.lat;
      const lng = event.lngLat.lng;

      // Data Zone click → place card (boundaries only; no AGR £).
      const dzHits =
        map.getLayer("data-zones-fill") &&
        map.getLayoutProperty("data-zones-fill", "visibility") === "visible"
          ? map.queryRenderedFeatures(event.point, {
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
        return;
      }

      // Layer popup: cadastral / public land / SVDLS site (ownership layers)
      try {
        const publicHits =
          map.getLayer("public-land-fill") &&
          map.getLayoutProperty("public-land-fill", "visibility") === "visible"
            ? map.queryRenderedFeatures(event.point, {
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
        const vdlHits =
          map.getLayer("vdl-fill") &&
          map.getLayoutProperty("vdl-fill", "visibility") === "visible"
            ? map.queryRenderedFeatures(event.point, {
                layers: ["vdl-fill"],
              })
            : [];
        const vdlProps = vdlHits[0]?.properties as
          | {
              name?: string;
              site_type?: string;
              size_ha?: number | string;
              site_code?: string;
              owner_class?: string;
              geometry_source?: string;
              geometry_source_label?: string;
              source?: string;
            }
          | undefined;
        const vdlSizeRaw = vdlProps?.size_ha;
        const vdlSizeHa =
          typeof vdlSizeRaw === "number"
            ? vdlSizeRaw
            : typeof vdlSizeRaw === "string" && vdlSizeRaw !== ""
              ? Number(vdlSizeRaw)
              : null;
        let parcelId: string | null = null;
        let areaSqm: number | null = null;
        let parcelSource: string | null = null;
        if (map.getZoom() >= CADASTRAL_MIN_ZOOM) {
          try {
            const parcelBody = await apiJson<{
              features?: Array<{
                properties?: {
                  inspire_id?: string;
                  label?: string;
                  national_reference?: string;
                  area_sqm?: number;
                  source?: string;
                };
              }>;
              meta?: { source?: string; found?: boolean };
            }>(`/layers/parcels/at?lat=${lat}&lng=${lng}`);
            const props = parcelBody.features?.[0]?.properties;
            parcelId =
              props?.inspire_id ||
              props?.national_reference ||
              props?.label ||
              null;
            areaSqm =
              typeof props?.area_sqm === "number" ? props.area_sqm : null;
            parcelSource =
              props?.source || parcelBody.meta?.source || "ROS INSPIRE";
          } catch {
            /* popup is best-effort; place card still loads */
          }
        }
        const html = layerPopupHtml({
          parcelId,
          areaSqm,
          ownerType: publicProps?.owner_type || publicProps?.organisation || null,
          siteName: publicProps?.site_name || null,
          vdlName: vdlProps?.name || null,
          vdlSiteType: vdlProps?.site_type || null,
          vdlSizeHa:
            vdlSizeHa != null && Number.isFinite(vdlSizeHa) ? vdlSizeHa : null,
          vdlSiteCode: vdlProps?.site_code || null,
          vdlOwnerClass: vdlProps?.owner_class || null,
          vdlGeometrySource:
            vdlProps?.geometry_source_label ||
            vdlProps?.geometry_source ||
            null,
          source:
            vdlProps?.source ||
            publicProps?.source ||
            parcelSource ||
            (parcelId || publicProps || vdlProps
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
        }
      } catch {
        /* ignore popup failures */
      }

      // Public shell: location + stub place card only (no AGR £ / Wealth / tax).
      await inspectRef.current(lat, lng, { fly: false });
    });


    mapRef.current = map;
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
      setMapReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Public shell: never fetch /layers/councils (council AGR £ and rent £/m² stay internal).
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("council-fill")) return;
    map.setLayoutProperty("council-fill", "visibility", "none");
    map.setLayoutProperty("council-line", "visibility", "none");
    map.setFilter("council-fill", null);
    map.setFilter("council-line", null);
  }, [mapReady, choropleth]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (showVdl) url.searchParams.set("vacant", "1");
    else url.searchParams.delete("vacant");
    url.searchParams.delete("public");
    url.searchParams.delete("band");
    window.history.replaceState({}, "", url.toString());
  }, [showVdl]);

  // Scot-LAND squares grid
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("w3w-agr-fill")) return;
      map.setLayoutProperty("w3w-agr-fill", "visibility", vis);
      map.setLayoutProperty("w3w-agr-line", "visibility", vis);
    };

    if (!showCellGrid) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadGrid = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < 12) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/w3w-grid?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&scenario=${scenario}&max_cells=200`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          (map.getSource("w3w-agr-grid") as GeoJSONSource)?.setData(data);
          setVis("visible");
        })
        .catch(() => {
          if (!cancelled) setVis("none");
        })
        .finally(() => {
          inFlight = false;
          if (!cancelled) setLayerBusy(false);
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadGrid, 700);
    };

    loadGrid();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showCellGrid, scenario]);

  // Data Zone boundaries (simplified GeoJSON by bbox — outlines only, no AGR £)
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
          (map.getSource("data-zones-overlay") as GeoJSONSource)?.setData(data);
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

  // SVDLS vacant / derelict overlay (OGL survey polygons)
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;

    const setVis = (vis: "visible" | "none") => {
      if (!map.getLayer("vdl-fill")) return;
      map.setLayoutProperty("vdl-fill", "visibility", vis);
      map.setLayoutProperty("vdl-line", "visibility", vis);
    };

    if (!showVdl) {
      setVis("none");
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadVdl = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < VDL_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      setLayerBusy(true);
      const path =
        `/layers/open/vdl?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=80`;
      void apiJson<GeoJSON.FeatureCollection>(path)
        .then((data) => {
          if (cancelled) return;
          (map.getSource("vdl-overlay") as GeoJSONSource)?.setData(data);
          setVis("visible");
          setLayerNotice(null);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setVis("none");
          if (err instanceof ApiError && err.status === 503) {
            setLayerNotice(
              "Vacant and derelict overlay is not available right now (SVDLS source unavailable). Gaps are not filled with guesses.",
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
      timer = setTimeout(loadVdl, 700);
    };

    loadVdl();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showVdl]);

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
          (map.getSource("public-land-overlay") as GeoJSONSource)?.setData(data);
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

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map) return;
    const sync = () => {
      const zoom = map.getZoom();
      const close = zoom >= CADASTRAL_MIN_ZOOM;
      if (map.isMoving()) return;
      if (!boundariesTouched.current) {
        setShowBoundaries(close);
      }
      // public_crown stays off: SG 2024 dashboard licence is unverified/not open
      if (!dataZonesTouched.current) {
        setShowDataZones(zoom >= DATA_ZONE_MIN_ZOOM);
      }
    };
    sync();
    map.on("zoomend", sync);
    map.on("moveend", sync);
    return () => {
      map.off("zoomend", sync);
      map.off("moveend", sync);
    };
  }, [mapReady]);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("parcels-wms")) return;
    // Cadastral routes are always mounted (not the optional AGR router).
    const vis = showBoundaries ? "visible" : "none";
    map.setLayoutProperty("parcels-wms", "visibility", vis);
    if (map.getLayer("parcels-postgis-fill")) {
      map.setLayoutProperty("parcels-postgis-fill", "visibility", vis);
    }
    if (map.getLayer("parcels-postgis-line")) {
      map.setLayoutProperty("parcels-postgis-line", "visibility", vis);
    }
  }, [mapReady, showBoundaries]);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getSource("parcels-postgis")) return;

    const setVis = (visibility: "visible" | "none") => {
      if (map.getLayer("parcels-postgis-fill")) {
        map.setLayoutProperty("parcels-postgis-fill", "visibility", visibility);
      }
      if (map.getLayer("parcels-postgis-line")) {
        map.setLayoutProperty("parcels-postgis-line", "visibility", visibility);
      }
    };

    if (!showBoundaries) {
      setVis("none");
      (map.getSource("parcels-postgis") as GeoJSONSource)?.setData(emptyCollection);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const loadParcels = () => {
      if (cancelled || !mapRef.current || inFlight) return;
      const b = map.getBounds();
      if (!b) return;
      if (map.getZoom() < CADASTRAL_MIN_ZOOM) {
        setVis("none");
        return;
      }
      inFlight = true;
      const path =
        `/layers/parcels?south=${b.getSouth()}&west=${b.getWest()}` +
        `&north=${b.getNorth()}&east=${b.getEast()}&max_features=200`;
      void apiJson<GeoJSON.FeatureCollection & { meta?: { fixture_scoped?: boolean } }>(
        path,
      )
        .then((data) => {
          if (cancelled) return;
          (map.getSource("parcels-postgis") as GeoJSONSource)?.setData(data);
          setVis("visible");
          // Fixture-scoped CI loads are honest gaps, not national RoS titles.
          if (data.meta?.fixture_scoped) {
            setLayerNotice(
              "Cadastral PostGIS load is fixture-scoped (synthetic CI polygons). Live WMS still shows registered extents where available.",
            );
          } else {
            setLayerNotice(null);
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          (map.getSource("parcels-postgis") as GeoJSONSource)?.setData(
            emptyCollection,
          );
          // 503 = table empty: keep WMS tiles; do not invent polygons.
          if (err instanceof ApiError && err.status === 503) {
            setLayerNotice(
              "Local cadastral PostGIS table is empty. Live RoS WMS tiles still draw registered extents where the view service answers.",
            );
          }
        })
        .finally(() => {
          inFlight = false;
        });
    };

    const onMove = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(loadParcels, 700);
    };

    loadParcels();
    map.on("moveend", onMove);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      map.off("moveend", onMove);
    };
  }, [mapReady, showBoundaries]);

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
      if (
        !on ||
        layer.kind === "raster" ||
        contextLoaded.current.has(layer.id) ||
        contextFlight.current.has(layer.id)
      ) {
        continue;
      }
      contextFlight.current.add(layer.id);
      void apiJson<
        GeoJSON.FeatureCollection & { meta?: { ok?: boolean; note?: string } }
      >(`/layers/context/${layer.id}`)
        .then((data) => {
          contextFlight.current.delete(layer.id);
          if (cancelled || data?.type !== "FeatureCollection") return;
          const source = map.getSource(`${layer.id}-src`) as GeoJSONSource | undefined;
          source?.setData(data);
          if (data.meta?.ok === false) {
            setContextNote(data.meta.note || "One layer did not load.");
            return;
          }
          contextLoaded.current.add(layer.id);
        })
        .catch(() => {
          contextFlight.current.delete(layer.id);
          if (!cancelled) setContextNote("One layer did not load.");
        });
    }
    return () => {
      cancelled = true;
      contextFlight.current.clear();
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

  const placeOpen = Boolean(placeStub || result || error);

  return (
    <div
      className={
        toolsOpen
          ? placeOpen
            ? "app-shell w3w-shell tools-open place-open"
            : "app-shell w3w-shell tools-open"
          : placeOpen
            ? "app-shell w3w-shell place-open"
            : "app-shell w3w-shell"
      }
    >
      <div className="map-stage">
      <div className="map-wrap">
        <div id="map" ref={mapContainer} />
      </div>

      <header className="hud-top" ref={headerRef}>
        <div className="hud-brand">
          <a className="hud-wordmark" href="/" aria-label="Scot-LAND">
            <img src="/scot-land-mark.png" alt="Scot-LAND" />
          </a>
        </div>
        <button
          type="button"
          className={toolsOpen ? "hud-layers-btn on" : "hud-layers-btn"}
          aria-pressed={toolsOpen}
          onClick={() => setToolsOpen((v) => !v)}
          data-testid="hud-ledger-btn"
        >
          Ledger
        </button>
        <button
          type="button"
          className={mapStyle === "satellite" ? "hud-layers-btn on" : "hud-layers-btn"}
          aria-pressed={mapStyle === "satellite"}
          title={
            mapStyle === "satellite"
              ? "Switch to streets map"
              : "Switch to satellite imagery"
          }
          onClick={() =>
            setMapStyle((current) =>
              current === "streets" ? "satellite" : "streets",
            )
          }
        >
          Satellite
        </button>
        <button
          type="button"
          className="hud-layers-btn"
          title="Use my location"
          onClick={() => locateMe()}
        >
          Locate
        </button>
        <div
          className={
            suggestions.length || suggestNote || suggesting
              ? "hud-search-dock open"
              : "hud-search-dock"
          }
        >
        <div className={loading || suggesting ? "hud-search loading" : "hud-search"}>
          <label className="sr-only" htmlFor="place-query">
            Search a postcode, place name, or coordinates
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
            placeholder={
              agrAvailable === false
                ? "Postcode or coordinates, e.g. G2 1DU"
                : "Postcode, place, or coordinates"
            }
            title="Search a Scottish postcode, place name, or lat, lng"
            onChange={(event) => {
              setQuery(event.target.value);
              scheduleSuggest(event.target.value);
            }}
            onBlur={() => {
              window.setTimeout(() => {
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
              } else if (event.key === "Escape" && (suggestions.length || suggestNote)) {
                event.preventDefault();
                event.stopPropagation();
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
            onClick={() => void runSearch()}
          >
            {loading ? "…" : "Search"}
          </button>
        </div>
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
        <nav className="hud-nav">
          <a href="/methodology">About</a>
        </nav>
      </header>

      <aside
        className={legendOpen ? "hud-scotland legend-open" : "hud-scotland"}
        aria-label="Land rent"
        ref={scotlandRef}
      >
        <div className="hud-scotland-stack">
          <button
            type="button"
            className="hud-scotland-fold"
            aria-expanded={legendOpen}
            aria-controls="hud-scotland-body"
            onClick={() => setLegendOpen((open) => !open)}
          >
            <span className="hud-scotland-fold-show">Show legend</span>
            <span className="hud-scotland-fold-hide">Hide legend</span>
          </button>
          <div className="hud-scotland-body" id="hud-scotland-body">
            <p className="hud-scotland-job">Find a place</p>
            <p className="hud-scotland-lead">
              Search a postcode, place or coordinates — or click the map.
            </p>
            <p className="hud-scotland-note">
              Modelled Annual Ground Rent (council charges and rent £/m²) and tax
              scenarios are not shown on the public map. Ownership and place
              details follow in later updates.
            </p>
            <p className="hud-scotland-foot">
              Research map, not a rates bill.{" "}
              <a href="/methodology">About</a>
            </p>
          </div>
        </div>
      </aside>

      {apiOk === false && (
        <div className="hud-banner">
          <span>{SERVICE_BUSY}</span>
          <button
            type="button"
            className="api-retry"
            onClick={() => void pingApi().then((s) => setApiOk(s.ok))}
          >
            Retry
          </button>
        </div>
      )}

      {toolsOpen && (
        <aside className="hud-card hud-tools" aria-label="Natural capital ledger">
          <div className="layer-panel">
            <LedgerPanel
              className="ledger-panel-in-shell"
              enabled={ledgerEnabled}
              onEnabledChange={onLedgerEnabledChange}
            />
            <p className="layer-meta" data-testid="public-agr-withheld">
              Modelled Annual Ground Rent (including council-area charges and
              rent per square metre) is not shown on the public map. AGR £
              stays internal at Data Zone band level until yield calibration.
              Shadow ledger totals stay separate and are never summed into the
              headline.
            </p>
            {layerNotice && <p className="layer-meta">{layerNotice}</p>}
            {contextNote && <p className="layer-meta">{contextNote}</p>}
            {CONTEXT_LAYERS.filter((layer) => contextOn[layer.id]).map((layer) => (
              <p key={layer.id} className="layer-meta">
                {layer.attribution}
              </p>
            ))}
          </div>
        </aside>
      )}
          {placeStub ? (
            <PlaceCardStub
              place={placeStub}
              loading={placeLoading}
              error={error}
              onClose={() => clearPlace()}
            />
          ) : error ? (
            <aside className="hud-card hud-place place-card-stub" aria-label="Place">
              <button
                type="button"
                className="hud-close"
                title="Close (Esc)"
                onClick={() => clearPlace()}
              >
                ×
              </button>
              <p className="error-line">{error}</p>
              <p className="meta">
                Try a Scottish postcode, place name, coordinates, or click the map.
              </p>
            </aside>
          ) : null}
      </div>
      <MapStampFooter />
    </div>
  );
}

