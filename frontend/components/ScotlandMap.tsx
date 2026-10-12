"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import maplibregl, {
  Map,
  GeoJSONSource,
  ExpressionSpecification,
  FilterSpecification,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import AgrBreakdown, {
  AgrResult,
  MapStampFooter,
  PlaceFiscal,
  ScenarioId,
} from "./AgrBreakdown";
import { WealthInspector, type WealthInspectorData } from "./WealthInspector";
import { useWealthApi } from "../lib/useWealthApi";
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
  visitorFacingError,
} from "../lib/api";
import { CONTEXT_LAYERS } from "../lib/contextLayers";

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

type StoryId = "who_pays" | "rent_intensity";

type RentBand = "low" | "mid" | "high";

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

const STORIES: Array<{ id: StoryId; label: string; metric: MetricId; blurb: string }> = [
  {
    id: "who_pays",
    label: "Annual Ground Rent",
    metric: "gross_liability",
    blurb: "The yearly rent of the land alone.",
  },
  {
    id: "rent_intensity",
    label: "Rent per square metre",
    metric: "rent_per_sqm",
    blurb: "The rent for each square metre of land.",
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
  const [choropleth, setChoropleth] = useState<MetricId | "off">("gross_liability");
  const [showBoundaries, setShowBoundaries] = useState(false);
  const [showCellGrid] = useState(false);
  const [showVdl, setShowVdl] = useState(false);
  const [showPublicLand, setShowPublicLand] = useState(false);
  const [layerNotice, setLayerNotice] = useState<string | null>(null);
  const publicLandTouched = useRef(false);
  const layerPopupRef = useRef<maplibregl.Popup | null>(null);

  // Georgist Wealth State
  const { lookupWealthAt, isLoading: wealthLoading, failure: wealthFailure } = useWealthApi();
  const [wealthData, setWealthData] = useState<WealthInspectorData | null>(null);
  const [showWealthPanel, setShowWealthPanel] = useState(false);

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
  const [layerBusy, setLayerBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SquareResponse | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  // Legacy ground-rent router mounted? null = not known yet. Its endpoints are never called when false.
  const [agrAvailable, setAgrAvailable] = useState<boolean | null>(null);
  const [metricNote, setMetricNote] = useState<string | null>(null);
  const [activeStory, setActiveStory] = useState<StoryId>("who_pays");
  const [band, setBand] = useState<RentBand | null>(null);
  const [streetScale, setStreetScale] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [mapStyle, setMapStyle] = useState<"streets" | "satellite">("streets");
  const [legendOpen, setLegendOpen] = useState(false);
  const markerRef = useRef<maplibregl.Marker | null>(null);
  const parcelLabelRef = useRef<maplibregl.Marker | null>(null);
  const boundariesTouched = useRef(false);
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
      parcelLabelRef.current?.remove();
      parcelLabelRef.current = null;
      const labelAt = payload.parcel?.geometry
        ? polygonLabelPoint(payload.parcel.geometry)
        : null;
      const area = payload.agr?.parcel_area_sqm;
      const yearly = payload.agr ? parcelYearlyRent(payload) : null;
      if (labelAt && area != null && yearly != null) {
        const el = document.createElement("div");
        el.className = "parcel-map-label";
        el.textContent = `${Math.round(area).toLocaleString("en-GB")} m² · ${formatRent(yearly)}/year`;
        parcelLabelRef.current = new maplibregl.Marker({
          element: el,
          anchor: "top",
          offset: [0, 14],
        })
          .setLngLat(labelAt)
          .addTo(map);
      }
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

  // One path for a point (map click, Locate, postcode search, ?lat=&lng=): marker, optional fly,
  // shareable URL, then the data-zone lookup and the wealth panel. Needs no AGR router.
  const inspectPoint = useCallback(
    async (lat: number, lng: number, opts: { fly?: boolean } = {}) => {
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      const map = mapRef.current;
      if (map && opts.fly) {
        markerRef.current?.remove();
        markerRef.current = new maplibregl.Marker({ color: "#0076d3" })
          .setLngLat([lng, lat])
          .addTo(map);
        map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 15), essential: true });
      }
      if (typeof window !== "undefined") {
        const url = new URL(window.location.href);
        url.searchParams.set("lat", lat.toFixed(6));
        url.searchParams.set("lng", lng.toFixed(6));
        url.searchParams.delete("words");
        window.history.replaceState({}, "", url.toString());
      }
      setWealthData(null);
      setShowWealthPanel(true);
      const res = await lookupWealthAt(lat, lng);
      setWealthData(res.ok ? res.data : null);
    },
    [lookupWealthAt],
  );
  const inspectRef = useRef(inspectPoint);
  inspectRef.current = inspectPoint;

  const locateMe = useCallback(() => {
    if (!navigator.geolocation) {
      setError("This browser cannot share a location.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords;
        void fetchCapabilities().then((caps) => {
          if (caps.agr) {
            void fetchSquare(latitude, longitude);
            return;
          }
          setLoading(false);
          setError(null);
          void inspectRef.current(latitude, longitude, { fly: true });
        });
      },
      () => {
        setLoading(false);
        setError(
          "Location unavailable. Allow location access, or search a postcode.",
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    );
  }, [fetchSquare]);

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
      if (result || error) clearPlace();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toolsOpen, result, error, clearPlace]);

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
      `/postcode/${encodeURIComponent(postcode)}?scenario=${scenario}`,
    );
    const payload = (await response.json()) as SquareResponse;
    if (generation !== lookupGen.current) return;
        setAddressLine(null);
    applyResult(payload);
  };

  const openWords = async (words: string, generation: number) => {
    const response = await apiFetch(
      `/square?words=${encodeURIComponent(words)}&scenario=${scenario}`,
    );
    const payload = (await response.json()) as SquareResponse;
    if (generation !== lookupGen.current) return;
        setAddressLine(null);
    applyResult(payload);
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
        setAddressLine(body.label ?? null);
        await fetchSquare(body.lat, body.lng, undefined, true, generation);
      } else if (body.kind === "places" && body.matches && body.matches.length > 1) {
        clearPlace();
        const found = suggestionsFromLookup(body, q);
        setSuggestions(found.items);
        setActiveSuggest(found.items.length ? 0 : -1);
      } else {
        clearPlace();
        setError(body.note || "No place matched. Try a postcode, or click the map.");
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
        setAddressLine(item.label);
        await fetchSquare(item.lat, item.lng, undefined, true, generation);
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

  // Re-assess selection when scenario changes so the place rent stays current
  useEffect(() => {
    if (!result) return;
    void fetchSquare(result.square.lat, result.square.lng, scenario, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario]);

  const applyStory = (storyId: StoryId) => {
    const story = STORIES.find((s) => s.id === storyId);
    if (!story) return;
    setActiveStory(storyId);
    setChoropleth(story.metric);
  };

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

      map.addSource("public-land-overlay", {
        type: "geojson",
        data: emptyCollection,
        attribution:
          "Scottish Public and Crown Estate Land 2024. Five bodies only; not a title.",
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
        attribution: "© Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data. © Crown copyright and database right 2026.",
      });
      map.addLayer({
        id: "parcels-wms",
        type: "raster",
        source: "parcels-wms",
        minzoom: 14,
        paint: { "raster-opacity": 0.9, "raster-fade-duration": 0 },
        layout: { visibility: "none" },
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
      const qBand = params.get("band");
      if (qBand === "low" || qBand === "mid" || qBand === "high") {
        setBand(qBand);
      }
      if (params.get("public") === "1") {
        publicLandTouched.current = true;
        setShowPublicLand(true);
      } else if (params.get("public") === "0") {
        publicLandTouched.current = true;
        setShowPublicLand(false);
      }
      if (params.get("vacant") === "1") {
        setShowVdl(true);
      }
      if (qWords) {
        setQuery(qWords);
        void (async () => {
          if (!(await fetchCapabilities()).agr) return;
          try {
            const encoded = encodeURIComponent(qWords);
            const response = await apiFetch(
              `/square?words=${encoded}&scenario=full_agr`,
            );
            applyResult((await response.json()) as SquareResponse);
            setApiOk(true);
          } catch (err) {
            setError(visitorFacingError(err));
            if (isServiceFailure(err)) {
              void pingApi().then((s) => setApiOk(s.ok));
            }
          }
        })();
      } else if (qLat && qLng) {
        void fetchCapabilities().then((caps) => {
          if (caps.agr) void fetchSquare(Number(qLat), Number(qLng));
          else void inspectRef.current(Number(qLat), Number(qLng), { fly: true });
        });
      }
    });

    map.on("click", async (event) => {
      const lat = event.lngLat.lat;
      const lng = event.lngLat.lng;

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

      const hits = map.queryRenderedFeatures(event.point, {
        layers: ["w3w-agr-fill", "council-fill"],
      });
      const point =
        hits[0]?.properties?.lat != null && hits[0].layer?.id === "w3w-agr-fill"
          ? { lat: Number(hits[0].properties.lat), lng: Number(hits[0].properties.lng) }
          : { lat: event.lngLat.lat, lng: event.lngLat.lng };
      void fetchSquare(point.lat, point.lng);

      // Georgist wealth: point -> /layers/context/data-zones/at -> /georgist/wealth with the
      // real DZ2011 code (DZ2022 if only that is loaded). Never sends 'unknown'.
      await inspectRef.current(point.lat, point.lng);
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
      if (!caps.agr) setMetricNote("Council ground-rent layers aren't available on this server yet.");
    });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load multi-metric council data once per scenario
  const metricsMetaRef = useRef<
    Record<string, { label?: string; unit?: string; min?: number; max?: number }> | null
  >(null);

  useEffect(() => {
    if (!mapReady || agrAvailable !== true) return; // council layer is part of the optional AGR router
    const map = mapRef.current;
    if (!map) return;

    let cancelled = false;
    setLayerBusy(true);
    void apiJson<
      GeoJSON.FeatureCollection & {
        meta?: {
          metrics?: Record<
            string,
            { label?: string; unit?: string; min?: number; max?: number }
          >;
        };
      }
    >(`/layers/councils?scenario=${scenario}`)
      .then((data) => {
        if (cancelled) return;
        const src = map.getSource("council-metrics") as GeoJSONSource | undefined;
        if (!src) throw new Error("Map source missing — refresh the page");
        src.setData(data);
        metricsMetaRef.current = data.meta?.metrics ?? null;
        setApiOk(true);
        // Trigger paint via choropleth effect
        setMetricNote((prev) => prev ?? "Councils loaded");
      })
      .catch((err: unknown) => {
        setError(visitorFacingError(err));
        if (isServiceFailure(err)) {
          void pingApi().then((s) => {
            if (!cancelled) setApiOk(s.ok);
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLayerBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mapReady, scenario, agrAvailable]);

  // Paint / visibility when metric selection changes
  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("council-fill")) return;

    if (choropleth === "off") {
      map.setLayoutProperty("council-fill", "visibility", "none");
      map.setLayoutProperty("council-line", "visibility", "none");
      map.setFilter("council-fill", null);
      map.setFilter("council-line", null);
      setMetricNote(null);
      return;
    }

    const councilVisible = !streetScale;
    map.setLayoutProperty(
      "council-fill",
      "visibility",
      councilVisible ? "visible" : "none",
    );
    map.setLayoutProperty(
      "council-line",
      "visibility",
      councilVisible ? "visible" : "none",
    );
    const def = METRICS.find((m) => m.id === choropleth) ?? METRICS[0];
    map.setPaintProperty("council-fill", "fill-color", paintForMetric(def));
    const rent: FilterSpecification = [
      "coalesce",
      ["get", "annual_ground_rent_plot_gbp"],
      0,
    ];
    const bandFilter: FilterSpecification | null =
      band === "low"
        ? ["<", rent, 1500]
        : band === "mid"
          ? ["all", [">=", rent, 1500], ["<", rent, 4500]]
          : band === "high"
            ? [">=", rent, 4500]
            : null;
    map.setFilter("council-fill", bandFilter);
    map.setFilter("council-line", bandFilter);

    const meta = metricsMetaRef.current?.[choropleth];
    if (meta?.min != null && meta?.max != null) {
      setMetricNote(
        `${def.label}: ${formatRange(meta.min, meta.max, meta.unit ?? "")}`,
      );
    } else {
      setMetricNote(def.label);
    }
  }, [mapReady, choropleth, layerBusy, band, streetScale]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (showVdl) url.searchParams.set("vacant", "1");
    else url.searchParams.delete("vacant");
    if (showPublicLand) url.searchParams.set("public", "1");
    else url.searchParams.delete("public");
    if (band) url.searchParams.set("band", band);
    else url.searchParams.delete("band");
    window.history.replaceState({}, "", url.toString());
  }, [showVdl, showPublicLand, band]);

  // W3W cell grid
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
      setStreetScale(close);
      if (map.isMoving()) return;
      if (!boundariesTouched.current) {
        setShowBoundaries(close);
      }
      if (!publicLandTouched.current) {
        setShowPublicLand(zoom >= PUBLIC_LAND_MIN_ZOOM);
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
    map.setLayoutProperty(
      "parcels-wms",
      "visibility",
      showBoundaries && agrAvailable === true ? "visible" : "none", // tiles come from the optional AGR router
    );
  }, [mapReady, showBoundaries, agrAvailable]);

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

  const legendMetric =
    choropleth === "off"
      ? null
      : (METRICS.find((m) => m.id === choropleth) ?? null);

  return (
    <div
      className={
        toolsOpen
          ? result || error
            ? "app-shell tools-open place-open"
            : "app-shell tools-open"
          : result || error
            ? "app-shell place-open"
            : "app-shell"
      }
    >
      <div className="map-stage">
      <div className="map-wrap">
        <div id="map" ref={mapContainer} />
      </div>

      <WealthInspector
        isOpen={showWealthPanel}
        onClose={() => setShowWealthPanel(false)}
        data={wealthData}
        failure={wealthFailure}
        isLoading={wealthLoading}
      />

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
        >
          Layers
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
            Type part of an address or a postcode
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
            placeholder={agrAvailable === false ? "Postcode, e.g. G2 1DU" : "Address or postcode"}
            title="A title number is looked up only if it is in the open set"
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
            {agrAvailable !== true ? (
              <>
                <p className="hud-scotland-job">Data zones</p>
                <p className="hud-scotland-lead">
                  Click the map, search a postcode or use Locate to see the data zone at that point.
                </p>
                <p className="hud-scotland-note">
                  Surface land rent isn&apos;t published yet. When it is, it will be a research
                  estimate for each data zone.
                </p>
              </>
            ) : (
              <>
                <p className="hud-scotland-job">Annual Ground Rent</p>
                <p className="hud-scotland-lead">A charge on the land alone.</p>
              </>
            )}
            {agrAvailable === true && legendMetric && (
              <div className="map-legend">
                {legendMetric.id !== "gross_liability" && (
                  <p className="map-legend-title">{legendMetric.label}</p>
                )}
                <div
                  className="map-legend-bar"
                  style={{ background: legendGradient(legendMetric.stops) }}
                  aria-hidden="true"
                />
                <div className="map-legend-stops">
                  <span>{formatLegendStop(legendMetric.stops[0][0], legendMetric.id)}</span>
                  <span>
                    {formatLegendStop(
                      legendMetric.stops[legendMetric.stops.length - 1][0],
                      legendMetric.id,
                    )}
                  </span>
                </div>
                <p className="hud-scotland-note">{legendCaption(legendMetric.id)}</p>
              </div>
            )}
            <p className="hud-scotland-foot">
              {agrAvailable === true
                ? "Research estimate, not a rates bill. "
                : "Data zone boundaries: Scottish Government, OGL v3. "}
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
      <aside className="hud-card hud-tools" aria-label="Map layers">
        <div className="layer-panel">
              <p className="hud-tools-title">Map layers</p>

              <section className="layer-ownership" aria-label="Ownership and cadastre">
                <label className="layer-select-label">Ownership and cadastre</label>
                <p className="layer-meta">
                  RoS INSPIRE parcels, public-sector holdings, and SVDLS vacant
                  and derelict sites. Separate from Annual Ground Rent and
                  Surface Rent.
                </p>
                <div className="layer-chips">
                  <button
                    type="button"
                    className={showBoundaries ? "chip active" : "chip"}
                    data-testid="layer-cadastral"
                    onClick={() => {
                      boundariesTouched.current = true;
                      setShowBoundaries((v) => !v);
                    }}
                    title="RoS INSPIRE cadastral parcels. On by default from street zoom."
                  >
                    Cadastral parcels
                  </button>
                  <button
                    type="button"
                    className={showPublicLand ? "chip active" : "chip"}
                    data-testid="layer-public-land"
                    onClick={() => {
                      publicLandTouched.current = true;
                      setShowPublicLand((on) => !on);
                    }}
                    title="Five public and Crown bodies (SG 2024). On by default from regional zoom."
                  >
                    Public land
                  </button>
                  <button
                    type="button"
                    className={showVdl ? "chip active" : "chip"}
                    data-testid="layer-vdl"
                    onClick={() => setShowVdl((on) => !on)}
                    title="Scottish Vacant and Derelict Land Survey sites. Survey polygons, not a title."
                  >
                    Vacant and derelict
                  </button>
                </div>
                {showBoundaries && (
                  <p className="layer-meta">
                    © Crown copyright. Reproduced with the permission of Registers
                    of Scotland. Contains OS data. Registered extents only — not a
                    title sheet. Zoom {CADASTRAL_MIN_ZOOM}+.
                  </p>
                )}
                {showPublicLand && (
                  <>
                    <ul className="layer-legend" aria-label="Public land legend">
                      {PUBLIC_LAND_BODIES.map((body) => (
                        <li key={body.name}>
                          <span
                            className="layer-legend-swatch"
                            style={{ background: body.color }}
                            aria-hidden="true"
                          />
                          {body.name}
                        </li>
                      ))}
                    </ul>
                    <p className="layer-meta">
                      Scottish Public and Crown Estate Land 2024. Five bodies
                      only — not local-authority land, not a title. Gaps are
                      flagged, never guessed. Zoom {PUBLIC_LAND_MIN_ZOOM}+.
                    </p>
                  </>
                )}
                {showVdl && (
                  <>
                    <ul className="layer-legend" aria-label="Vacant and derelict legend">
                      {VDL_SITE_TYPES.map((site) => (
                        <li key={site.name}>
                          <span
                            className="layer-legend-swatch"
                            style={{ background: site.color }}
                            aria-hidden="true"
                          />
                          {site.name}
                        </li>
                      ))}
                    </ul>
                    <p className="layer-meta">
                      Scottish Vacant and Derelict Land Survey. Site-level as
                      published (OGL v3.0). Contains data from Improvement
                      Service under OGL, supplied by Scotland&apos;s local
                      planning authorities and Loch Lomond &amp; The Trossachs
                      National Park Authority. © Scottish Government. Survey
                      polygons, not a title. Owner class is a survey field.
                      Zoom {VDL_MIN_ZOOM}+.
                    </p>
                  </>
                )}
                {layerNotice && <p className="layer-meta">{layerNotice}</p>}
              </section>

              <label className="layer-select-label">The charge</label>
              <div className="layer-chips story-chips">
                {STORIES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    className={activeStory === s.id ? "chip active" : "chip"}
                    onClick={() => applyStory(s.id)}
                    title={s.blurb}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <p className="layer-meta">
                Filters the charge colour. Low is under £1,500 a year. High is £4,500 or more.
                Annual Ground Rent (residual) is not Surface Rent (la-calc).
              </p>
              <div className="layer-chips">
                {(["low", "mid", "high"] as RentBand[]).map((id) => (
                  <button
                    key={id}
                    type="button"
                    className={band === id ? "chip active" : "chip"}
                    onClick={() => setBand((cur) => (cur === id ? null : id))}
                    title="Filters the charge colour."
                  >
                    {id} rent
                  </button>
                ))}
              </div>
              {band && (
                <p className="layer-meta">Showing the {band} band of this charge.</p>
              )}
              {metricNote && choropleth !== "off" && (
                <p className="layer-meta">
                  {layerBusy ? "Loading…" : metricNote}
                </p>
              )}

              <label className="layer-select-label">The piece of land</label>
              <div className="layer-chips">
                <button
                  type="button"
                  className={showBoundaries ? "chip active" : "chip"}
                  onClick={() => {
                    boundariesTouched.current = true;
                    setShowBoundaries((v) => !v);
                  }}
                  title={agrAvailable === false
                    ? "Register outlines aren't available on this server yet."
                    : "Register outlines of neighbouring pieces of land. Zoom in."}
                  disabled={agrAvailable === false}
                >
                  Register outlines
                </button>
                {["urban-rural", "data-zones"].map((id) => {
                  const layer = CONTEXT_LAYERS.find((item) => item.id === id);
                  if (!layer) return null;
                  return (
                    <button
                      key={layer.id}
                      type="button"
                      className={contextOn[layer.id] ? "chip active" : "chip"}
                      title={layer.title}
                      onClick={() =>
                        setContextOn((cur) => ({ ...cur, [layer.id]: !cur[layer.id] }))
                      }
                    >
                      {layer.id === "urban-rural" ? "Town or countryside" : layer.label}
                    </button>
                  );
                })}
              </div>

              <details className="layer-fold">
                <summary>Around the land</summary>
                <p className="layer-meta">Context, not the charge.</p>
                <div className="layer-chips">
                  {["settlements", "woodland"].map((id) => {
                    const layer = CONTEXT_LAYERS.find((item) => item.id === id);
                    if (!layer) return null;
                    return (
                      <button
                        key={layer.id}
                        type="button"
                        className={contextOn[layer.id] ? "chip active" : "chip"}
                        title={layer.title}
                        onClick={() =>
                          setContextOn((cur) => ({ ...cur, [layer.id]: !cur[layer.id] }))
                        }
                      >
                        {layer.label}
                      </button>
                    );
                  })}
                  {CONTEXT_LAYERS.filter((layer) => layer.id === "flood").map((layer) => (
                    <button
                      key={layer.id}
                      type="button"
                      className={contextOn[layer.id] ? "chip active" : "chip"}
                      title={layer.title}
                      onClick={() =>
                        setContextOn((cur) => ({ ...cur, [layer.id]: !cur[layer.id] }))
                      }
                    >
                      Flood
                    </button>
                  ))}
                </div>
              </details>

              <details className="layer-fold">
                <summary>Sea and energy</summary>
                <p className="layer-meta">Context, not the charge.</p>
                <div className="layer-chips">
                  {CONTEXT_LAYERS.filter(
                    (layer) => layer.group === "Sea" || layer.group === "Energy",
                  ).map((layer) => (
                    <button
                      key={layer.id}
                      type="button"
                      className={contextOn[layer.id] ? "chip active" : "chip"}
                      title={layer.title}
                      onClick={() =>
                        setContextOn((cur) => ({ ...cur, [layer.id]: !cur[layer.id] }))
                      }
                    >
                      {layer.label}
                    </button>
                  ))}
                </div>
              </details>
              {CONTEXT_LAYERS.filter((layer) => contextOn[layer.id]).map((layer) => (
                <p key={layer.id} className="layer-meta">
                  {layer.attribution}
                </p>
              ))}
              {contextNote && <p className="layer-meta">{contextNote}</p>}
              <p className="layer-meta">
                Not drawn: land capability (James Hutton, all rights reserved).
                Small-area population, jobs, and Ordnance Survey roads, rail,
                airports and greenspace are not on this map yet. Wires, mains
                and broadband are
                not an open national map. Local development plan sites are not
                on this map: the national file is for public bodies and
                universities.
              </p>
            </div>
          </aside>
      )}
          {(result || error) && (
          <aside className="hud-card hud-place">
            <button
              type="button"
              className="hud-close"
              title="Close place (Esc)"
              onClick={() => clearPlace()}
            >
              ×
            </button>
            {error && <p className="error-line">{error}</p>}
            {result?.reason === "not_land" && (
              <>
                <p className="location-line">
                  {result.square.lat.toFixed(5)}, {result.square.lng.toFixed(5)}
                </p>
                <p className="headline-caption">The seabed is land.</p>
                {seabed === null ? (
                  <p className="meta">Looking up the published lease.</p>
                ) : seabed.failed ? (
                  <p className="headline-caption">The lease service did not answer.</p>
                ) : seabed.notes.length === 0 ? (
                  <p className="headline-caption">
                    No published lease rent falls on this point.
                  </p>
                ) : (
                  seabed.notes.map((note, index) => (
                    <p key={`${index}-${note.slice(0, 24)}`} className="meta">
                      {note}
                    </p>
                  ))
                )}
              </>
            )}
            {result?.agr && (
              <AgrBreakdown
                agr={result.agr}
                areaSqm={result.square.area_sqm}
                postcode={result.postcode?.postcode}
                placeLabel={addressLine}
                lat={result.square.lat}
                lng={result.square.lng}
                what3words={result.what3words}
                parcelLabel={
                  result.parcel?.properties?.label ?? result.agr.parcel_id
                }
                parcelAreaSqm={
                  result.parcel?.properties?.area_sqm ??
                  result.agr.parcel_area_sqm
                }
                fiscal={result.fiscal}
                platform={result.platform}
                locationClass={urbanRuralName}
                dataZone={dataZone}
                seabedNotes={seabed?.notes}
              />
            )}
          </aside>
          )}
      </div>
      <MapStampFooter />
    </div>
  );
}

function legendGradient(stops: [number, string][]): string {
  const min = stops[0][0];
  const max = stops[stops.length - 1][0];
  const span = max - min || 1;
  const parts = stops.map(([value, color]) => {
    const pct = ((value - min) / span) * 100;
    return `${color} ${pct}%`;
  });
  return `linear-gradient(to right, ${parts.join(", ")})`;
}

function formatLegendStop(value: number, id: MetricId): string {
  if (id === "agr_price_pct" || id === "land_share" || id === "simd") {
    return `${value}%`;
  }
  if (id === "pop_density") {
    return value >= 1000 ? `${value / 1000}k` : String(value);
  }
  const sign = value < 0 ? "\u2212" : "";
  const abs = Math.abs(value);
  if (id === "vacant_residual" && abs >= 1_000_000) {
    return `${sign}\u00a3${Math.round(abs / 1_000_000)}m`;
  }
  if (abs >= 1000) {
    return `${sign}\u00a3${Math.round(abs / 1000).toLocaleString("en-GB")}k`;
  }
  return `${sign}\u00a3${Math.round(abs)}`;
}

function parcelYearlyRent(payload: SquareResponse): number | null {
  if (!payload.agr) return null;
  const area = payload.agr.parcel_area_sqm;
  if (area == null || area <= 0 || !payload.parcel?.geometry) return null;
  const gross = payload.fiscal?.gross_plot_gbp;
  if (gross != null && gross > 0) return gross;
  const cell = payload.agr.economic_annual_rent_gbp;
  const active = payload.agr.scenarios.full_agr.annual_charge_gbp;
  const scale = cell > 0 ? active / cell : 1;
  const parcel = payload.agr.site_rental_per_sqm_gbp * area * scale;
  return parcel > 0 ? parcel : null;
}

function formatRent(value: number): string {
  if (value >= 100) return `£${Math.round(value).toLocaleString("en-GB")}`;
  return `£${value.toFixed(2)}`;
}

function polygonLabelPoint(
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon,
): [number, number] | null {
  const ring =
    geometry.type === "Polygon"
      ? geometry.coordinates[0]
      : geometry.coordinates[0]?.[0];
  if (!ring || ring.length === 0) return null;
  const last = ring.length - 1;
  const closed =
    ring[0][0] === ring[last][0] && ring[0][1] === ring[last][1] && last > 0;
  const count = closed ? last : ring.length;
  let x = 0;
  let y = 0;
  for (let i = 0; i < count; i += 1) {
    x += ring[i][0];
    y += ring[i][1];
  }
  return [x / count, y / count];
}

function legendCaption(id: MetricId): string {
  switch (id) {
    case "gross_liability":
    case "agr_plot":
      return "The colour is each council's town home plot. A click uses town or countryside at that point.";
    case "rent_per_sqm":
      return "Annual Ground Rent per square metre of land.";
    case "net_contribution":
      return "A typical plot set against one person's share. Teal is below that share. Orange is above it.";
    case "vacant_residual":
      return "Illustrative rent on surveyed vacant land in the council.";
    case "house_price":
      return "Average house price in the council, building and land together.";
    case "agr_price_pct":
      return "The plot's Annual Ground Rent as a share of the average house price.";
    case "land_share":
      return "The land share used in that council's calculation.";
    case "site_capital":
      return "Economic land value per square metre, after the speculative cut.";
    case "simd":
      return "Share of data zones in the most deprived fifth. Context only, not the charge.";
    case "pop_density":
      return "People per square kilometre. Context only, not the charge.";
    default:
      return "Research estimate, not a rates bill.";
  }
}

function formatRange(min: number, max: number, unit: string): string {
  const fmt = (n: number) => {
    if (unit.includes("%")) return `${n.toFixed(1)}%`;
    if (unit.includes("£") || unit.startsWith("£")) {
      if (Math.abs(n) >= 1000) return `£${Math.round(n).toLocaleString("en-GB")}`;
      return `£${n.toFixed(n >= 10 ? 0 : 2)}`;
    }
    if (Math.abs(n) >= 100) return Math.round(n).toLocaleString("en-GB");
    return n.toFixed(1);
  };
  const u = unit.includes("%") || unit.includes("£") ? "" : ` ${unit}`;
  return `${fmt(min)}–${fmt(max)}${u}`;
}


