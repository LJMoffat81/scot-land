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
  PlaceFiscal,
  ScenarioId,
} from "./AgrBreakdown";
import CoveragePanel, { CoverageLayer } from "./CoveragePanel";
import NationalStats from "./NationalStats";
import { ApiError, apiFetch, apiJson, pingApi } from "../lib/api";

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
  agr: AgrResult;
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

type AddressMatch = {
  lat: number;
  lng: number;
  street: string;
  housenumber: string;
  label: string;
};

type AddressLookup = {
  postcode: string;
  door: string;
  status: "one" | "many" | "none";
  matches: AddressMatch[];
  note: string;
};

type FiscalSummary = {
  enabled: boolean;
  scenario: string;
  basket: { total_gbp: number; lines: Array<{ label: string; annual_gbp: number }> };
  collection: { annual_gbp: number; method: string };
  surplus_gbp: number;
  revenue_neutral_or_better: boolean;
  dividend: { per_person_gbp: number; mode: string };
  remote_credit: { enabled: boolean; credit_gbp_per_person_year: number };
};

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

type StoryId =
  | "who_pays"
  | "net_position"
  | "rent_intensity"
  | "equity"
  | "prices"
  | "vacant_land";

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
    blurb: "The full charge on the land alone",
  },
  {
    id: "net_position",
    label: "Against one person's share",
    metric: "net_contribution",
    blurb: "Teal is below that share. Orange is above it.",
  },
  {
    id: "rent_intensity",
    label: "Rent per square metre",
    metric: "rent_per_sqm",
    blurb: "The charge for each square metre of land.",
  },
  {
    id: "prices",
    label: "Rent and house prices",
    metric: "agr_price_pct",
    blurb: "This rent as a share of the average house price.",
  },
  {
    id: "equity",
    label: "Deprivation",
    metric: "simd",
    blurb: "Share of areas in the most deprived fifth. Not the charge.",
  },
  {
    id: "vacant_land",
    label: "Vacant land",
    metric: "vacant_residual",
    blurb: "Surveyed vacant land in the council. Not a rates bill.",
  },
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

function looksLikePostcode(q: string): boolean {
  const t = q.trim().replace(/\s+/g, "").toUpperCase();
  return /^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$/i.test(t) || /^[A-Z]{1,2}\d/i.test(t);
}

export default function ScotlandMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const [query, setQuery] = useState("");
  const [postcodeReady, setPostcodeReady] = useState<string | null>(null);
  const [postcodeCentre, setPostcodeCentre] = useState<{ lat: number; lng: number } | null>(
    null,
  );
  const [doorQuery, setDoorQuery] = useState("");
  const [doorMatches, setDoorMatches] = useState<AddressMatch[] | null>(null);
  const [addressLine, setAddressLine] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>("full_agr");
  const [choropleth, setChoropleth] = useState<MetricId | "off">("gross_liability");
  const [showBoundaries, setShowBoundaries] = useState(false);
  const [showCellGrid, setShowCellGrid] = useState(false);
  const [showVdl, setShowVdl] = useState(false);
  const [showPublicLand, setShowPublicLand] = useState(false);
  const [showMethod, setShowMethod] = useState(false);
  const [layerBusy, setLayerBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SquareResponse | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [reportDownloading, setReportDownloading] = useState(false);
  const [metricNote, setMetricNote] = useState<string | null>(null);
  const [fiscalSummary, setFiscalSummary] = useState<FiscalSummary | null>(null);
  const [activeStory, setActiveStory] = useState<StoryId>("who_pays");
  const [coverageLive, setCoverageLive] = useState<CoverageLayer[]>([]);
  const [coverageGaps, setCoverageGaps] = useState<CoverageLayer[]>([]);
  const [coverageOpen, setCoverageOpen] = useState(false);
  const [band, setBand] = useState<RentBand | null>(null);
  const [statsOpen, setStatsOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [mapStyle, setMapStyle] = useState<"streets" | "satellite">("streets");
  const markerRef = useRef<maplibregl.Marker | null>(null);

  const applyResult = useCallback((payload: SquareResponse) => {
    setResult(payload);
    setScenario(payload.agr.active_scenario);

    const map = mapRef.current;
    if (map) {
      markerRef.current?.remove();
      markerRef.current = new maplibregl.Marker({ color: "#0076d3" })
        .setLngLat([payload.square.lng, payload.square.lat])
        .addTo(map);
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
      if (targetZoom >= 14) setShowCellGrid(true);
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
      keepDoor = false,
    ) => {
      if (!keepDoor) {
        setPostcodeReady(null);
        setPostcodeCentre(null);
        setDoorQuery("");
        setDoorMatches(null);
        setAddressLine(null);
      }
      setLoading(true);
      setError(null);
      const sc = nextScenario ?? scenario;
      try {
        const response = await apiFetch(
          `/square?lat=${nextLat}&lng=${nextLng}&scenario=${sc}`,
        );
        applyResult((await response.json()) as SquareResponse);
        setApiOk(true);
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(
          message.toLowerCase().includes("outside scotland")
            ? "That point is outside Scotland. Search a Scottish postcode or click the map."
            : message,
        );
        if (
          err instanceof ApiError &&
          (err.status == null || err.status >= 500)
        ) {
          setApiOk(false);
        }
      } finally {
        setLoading(false);
      }
    },
    [applyResult, scenario],
  );

  const clearPlace = useCallback(() => {
    setResult(null);
    setError(null);
    setPostcodeReady(null);
    setPostcodeCentre(null);
    setDoorQuery("");
    setDoorMatches(null);
    setAddressLine(null);
    markerRef.current?.remove();
    markerRef.current = null;
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

  const locateMe = useCallback(() => {
    if (!navigator.geolocation) {
      setError("This browser cannot share a location.");
      return;
    }
    setLoading(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        void fetchSquare(pos.coords.latitude, pos.coords.longitude);
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

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    try {
      const isWords = /^[a-z]+\.[a-z]+\.[a-z]+$/i.test(q.replace(/^\/+/, ""));
      if (isWords) {
        const encoded = encodeURIComponent(q.replace(/^\/+/, ""));
        const response = await apiFetch(
          `/square?words=${encoded}&scenario=${scenario}`,
        );
        applyResult((await response.json()) as SquareResponse);
        setPostcodeReady(null);
        setPostcodeCentre(null);
        setDoorQuery("");
        setDoorMatches(null);
        setAddressLine(null);
      } else if (looksLikePostcode(q) || q.length >= 5) {
        const encoded = encodeURIComponent(q);
        const response = await apiFetch(
          `/postcode/${encoded}?scenario=${scenario}`,
        );
        const payload = (await response.json()) as SquareResponse;
        applyResult(payload);
        setPostcodeReady(payload.postcode?.postcode ?? null);
        setPostcodeCentre(
          payload.postcode?.postcode
            ? { lat: payload.square.lat, lng: payload.square.lng }
            : null,
        );
        setDoorQuery("");
        setDoorMatches(null);
        setAddressLine(null);
      } else {
        setError("Enter a postcode (e.g. EH1 1YZ) or What3Words (word.word.word)");
        setLoading(false);
        return;
      }
      setApiOk(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      if (err instanceof ApiError && (err.status == null || err.status >= 500)) {
        setApiOk(false);
      }
    } finally {
      setLoading(false);
    }
  };

  const pickDoor = (match: AddressMatch) => {
    setDoorMatches(null);
    setAddressLine(match.label);
    setError(null);
    void fetchSquare(match.lat, match.lng, undefined, true);
  };

  const runDoor = async () => {
    const door = doorQuery.trim();
    if (!postcodeReady || !door) return;
    setLoading(true);
    setError(null);
    setDoorMatches(null);
    try {
      const centre = postcodeCentre
        ? `&lat=${postcodeCentre.lat}&lng=${postcodeCentre.lng}`
        : "";
      const response = await apiFetch(
        `/address?postcode=${encodeURIComponent(postcodeReady)}&door=${encodeURIComponent(door)}${centre}`,
      );
      const body = (await response.json()) as AddressLookup;
      if (body.status === "none" || body.matches.length === 0) {
        setAddressLine(null);
        setDoorMatches(null);
        if (postcodeCentre) {
          await fetchSquare(postcodeCentre.lat, postcodeCentre.lng, undefined, true);
        } else {
          setLoading(false);
        }
        setError(
          body.note ||
            "That door is not in the open address set. The map stays on the postcode centre.",
        );
        return;
      }
      if (body.status === "many") {
        setDoorMatches(body.matches);
        setLoading(false);
        return;
      }
      pickDoor(body.matches[0]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Address search failed";
      setError(message);
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      void pingApi().then((s) => {
        if (!cancelled) setApiOk(s.ok);
      });
    };
    tick();
    const id = setInterval(tick, 20000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // National fiscal dashboard
  useEffect(() => {
    let cancelled = false;
    void apiJson<FiscalSummary>(`/fiscal/summary?scenario=${scenario}`)
      .then((data) => {
        if (!cancelled) setFiscalSummary(data);
      })
      .catch(() => {
        if (!cancelled) setFiscalSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [scenario]);

  useEffect(() => {
    let cancelled = false;
    void apiJson<{ live: CoverageLayer[]; gaps: CoverageLayer[] }>("/platform/gaps")
      .then((data) => {
        if (cancelled) return;
        setCoverageLive(data.live ?? []);
        setCoverageGaps(data.gaps ?? []);
      })
      .catch(() => {
        if (!cancelled) {
          setCoverageLive([]);
          setCoverageGaps([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Re-assess selection when scenario changes so fiscal gross/net update
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
    if (storyId === "vacant_land") {
      setShowVdl(true);
    }
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (storyId === "vacant_land") {
        url.searchParams.set("story", "vacant_land");
      } else {
        url.searchParams.delete("story");
      }
      window.history.replaceState({}, "", url.toString());
    }
  };

  useEffect(() => {
    if (!mapContainer.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainer.current,
      // CARTO's raster tiles now stamp "API key required" unless a key is set.
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [-4.2, 56.8],
      zoom: 6.2,
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.getCanvas().style.cursor = "pointer";

    map.on("load", () => {
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
          "SVDLS © Scottish Government (OGL v3.0). Survey polygons, not a title.",
      });
      map.addLayer({
        id: "vdl-fill",
        type: "fill",
        source: "vdl-overlay",
        layout: { visibility: "none" },
        paint: {
          "fill-color": "#c45c26",
          "fill-opacity": 0.38,
        },
      });
      map.addLayer({
        id: "vdl-line",
        type: "line",
        source: "vdl-overlay",
        layout: { visibility: "none" },
        paint: { "line-color": "#7a2e00", "line-width": 1.1, "line-opacity": 0.9 },
      });

      map.addSource("parcels-wms", {
        type: "raster",
        tiles: ["/api/parcels/tiles/{z}/{x}/{y}"],
        tileSize: 256,
        minzoom: 14,
        maxzoom: 19,
        scheme: "xyz",
        attribution: "© Registers of Scotland (INSPIRE cadastral parcels)",
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
        attribution: "Tiles © Esri",
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
      const qStory = params.get("story");
      if (qStory === "vacant_land") {
        setActiveStory("vacant_land");
        setChoropleth("vacant_residual");
        setShowVdl(true);
      }
      if (params.get("vacant") === "1") setShowVdl(true);
      if (params.get("public") === "0") setShowPublicLand(false);
      if (params.get("public") === "1") setShowPublicLand(true);
      const qBand = params.get("band");
      if (qBand === "low" || qBand === "mid" || qBand === "high") {
        setBand(qBand);
      }
      if (qWords) {
        setQuery(qWords);
        void (async () => {
          try {
            const encoded = encodeURIComponent(qWords);
            const response = await apiFetch(
              `/square?words=${encoded}&scenario=full_agr`,
            );
            applyResult((await response.json()) as SquareResponse);
            setApiOk(true);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Lookup failed");
          }
        })();
      } else if (qLat && qLng) {
        void fetchSquare(Number(qLat), Number(qLng));
      }
    });

    map.on("click", (event) => {
      const hits = map.queryRenderedFeatures(event.point, {
        layers: ["w3w-agr-fill", "council-fill"],
      });
      if (hits[0]?.properties?.lat != null && hits[0].layer?.id === "w3w-agr-fill") {
        void fetchSquare(Number(hits[0].properties.lat), Number(hits[0].properties.lng));
        return;
      }
      void fetchSquare(event.lngLat.lat, event.lngLat.lng);
    });

    mapRef.current = map;
    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load multi-metric council data once per scenario
  const metricsMetaRef = useRef<
    Record<string, { label?: string; unit?: string; min?: number; max?: number }> | null
  >(null);

  useEffect(() => {
    if (!mapReady) return;
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
      .catch((err: Error) => {
        setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLayerBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [mapReady, scenario]);

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

    map.setLayoutProperty("council-fill", "visibility", "visible");
    map.setLayoutProperty("council-line", "visibility", "visible");
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
  }, [mapReady, choropleth, layerBusy, band]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (showVdl) url.searchParams.set("vacant", "1");
    else url.searchParams.delete("vacant");
    if (showPublicLand) url.searchParams.set("public", "1");
    else url.searchParams.set("public", "0");
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
      if (map.getZoom() < 8) {
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
      if (map.getZoom() < 6) {
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
    if (!map?.getLayer("parcels-wms")) return;
    map.setLayoutProperty(
      "parcels-wms",
      "visibility",
      showBoundaries ? "visible" : "none",
    );
  }, [mapReady, showBoundaries]);

  useEffect(() => {
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("council-method")) return;
    map.setLayoutProperty(
      "council-method",
      "visibility",
      showMethod && choropleth !== "off" ? "visible" : "none",
    );
  }, [mapReady, showMethod, choropleth]);

  const downloadReport = async (format: "markdown" | "json") => {
    if (!result) return;
    setReportDownloading(true);
    setError(null);
    try {
      const path =
        `/assessment/report?lat=${result.square.lat}&lng=${result.square.lng}` +
        `&scenario=${scenario}&format=${format === "json" ? "json" : "markdown"}`;
      const response = await apiFetch(path);
      const base = `scot-land-${result.square.lat.toFixed(5)}_${result.square.lng.toFixed(5)}`;
      if (format === "json") {
        const data = await response.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], {
          type: "application/json",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${base}.json`;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        const text = await response.text();
        const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `${base}.md`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report download failed");
    } finally {
      setReportDownloading(false);
    }
  };

  const valueMetrics = METRICS.filter((m) => m.group === "value");
  const contextMetrics = METRICS.filter((m) => m.group === "context");
  const legendMetric =
    choropleth === "off"
      ? null
      : (METRICS.find((m) => m.id === choropleth) ?? null);

  return (
    <div className="app-shell">
      <div className="map-wrap">
        <div id="map" ref={mapContainer} />
        {!result && apiOk !== false && (
          <div className="map-hint">Click a place for its Annual Ground Rent</div>
        )}
      </div>

      <header className="hud-top">
        <div className="hud-brand">
          <a className="hud-wordmark" href="/" aria-label="Scot-LAND">
            <img src="/scot-land-mark.png" alt="Scot-LAND" />
          </a>
        </div>
        <button
          type="button"
          className={toolsOpen ? "hud-layers-btn on" : "hud-layers-btn"}
          onClick={() => setToolsOpen((v) => !v)}
        >
          Layers
        </button>
        <button
          type="button"
          className={mapStyle === "satellite" ? "hud-layers-btn on" : "hud-layers-btn"}
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
            loading
              ? postcodeReady
                ? "hud-search has-door loading"
                : "hud-search loading"
              : postcodeReady
                ? "hud-search has-door"
                : "hud-search"
          }
        >
          <label className="sr-only" htmlFor="place-query">
            Search a Scottish postcode
          </label>
          <input
            id="place-query"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void runSearch();
            }}
            placeholder="Search a Scottish postcode"
            disabled={loading || apiOk === false}
          />
          {postcodeReady && (
            <>
              <label className="sr-only" htmlFor="door-query">
                Door number
              </label>
              <input
                id="door-query"
                value={doorQuery}
                onChange={(e) => setDoorQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runDoor();
                }}
                placeholder="Door number"
                disabled={loading || apiOk === false}
              />
              <button
                type="button"
                className="hud-search-go"
                disabled={loading || apiOk === false || !doorQuery.trim()}
                onClick={() => void runDoor()}
              >
                {loading ? "…" : "Find"}
              </button>
            </>
          )}
          <button
            type="button"
            className="hud-search-go"
            disabled={loading || apiOk === false || !query.trim()}
            onClick={() => void runSearch()}
          >
            {loading ? "…" : "Search"}
          </button>
          {doorMatches && doorMatches.length > 1 && (
            <ul className="door-matches">
              {doorMatches.map((match) => (
                <li key={`${match.lat},${match.lng},${match.label}`}>
                  <button type="button" onClick={() => pickDoor(match)}>
                    {match.label}
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

      <aside className="hud-scotland" aria-label="Scotland illustration">
        <p className="hud-scotland-job">Annual Ground Rent</p>
        <p className="hud-scotland-lead">A charge on the land alone.</p>
        {fiscalSummary?.enabled && scenario !== "full_agr" && (
          <div className="hud-scotland-grid">
            <div>
              <span className="fd-label">Listed taxes</span>
              <span className="fd-value">
                {formatBn(fiscalSummary.basket.total_gbp)}
              </span>
            </div>
            <div>
              <span className="fd-label">Scaled charge</span>
              <span className="fd-value">
                {formatBn(fiscalSummary.collection.annual_gbp)}
              </span>
            </div>
            <div>
              <span className="fd-label">
                {fiscalSummary.surplus_gbp >= 0 ? "Above the list" : "Short of the list"}
              </span>
              <span className="fd-value">
                {formatBn(Math.abs(fiscalSummary.surplus_gbp))}
              </span>
            </div>
          </div>
        )}
        {legendMetric && (
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
          Research estimate, not a rates bill. <a href="/methodology">About</a>
        </p>
      </aside>

      {apiOk === false && (
        <div className="hud-banner">
          <span>API offline — start backend on port 8000</span>
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
      <aside className="hud-card hud-tools">
        <div className="layer-panel">
              <p className="hud-tools-title">Map layers</p>
              <label className="layer-select-label">Basemap</label>
              <div className="layer-chips">
                <button
                  type="button"
                  className={mapStyle === "streets" ? "chip active" : "chip"}
                  onClick={() => setMapStyle("streets")}
                >
                  Streets
                </button>
                <button
                  type="button"
                  className={mapStyle === "satellite" ? "chip active" : "chip"}
                  onClick={() => setMapStyle("satellite")}
                >
                  Satellite
                </button>
              </div>
              <label className="layer-select-label">Colour</label>
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

              <label className="layer-select-label">Filter</label>
              <div className="layer-chips">
                <button
                  type="button"
                  className={showVdl ? "chip active" : "chip"}
                  onClick={() => setShowVdl((v) => !v)}
                  title="Surveyed vacant and derelict land"
                >
                  Vacant
                </button>
                <button
                  type="button"
                  className={showPublicLand ? "chip active" : "chip"}
                  onClick={() => setShowPublicLand((v) => !v)}
                  title="Show five-body public / Crown overlay"
                >
                  Public
                </button>
                {(["low", "mid", "high"] as RentBand[]).map((id) => (
                  <button
                    key={id}
                    type="button"
                    className={band === id ? "chip active" : "chip"}
                    onClick={() => setBand((cur) => (cur === id ? null : id))}
                    title="Filter councils by plot AGR band (low < £1,500, mid, high ≥ £4,500)"
                  >
                    {id} rent
                  </button>
                ))}
              </div>
              {band && (
                <p className="layer-meta">
                  Showing {band} rent-band councils only. Ownership is public or
                  unknown — never labelled private from this overlay.
                </p>
              )}

              <label className="layer-select-label" htmlFor="choropleth">
                Colour map by
              </label>
              <select
                id="choropleth"
                className="layer-select"
                value={choropleth}
                onChange={(e) =>
                  setChoropleth(e.target.value as MetricId | "off")
                }
              >
                <optgroup label="Fiscal">
                  {METRICS.filter((m) => m.group === "fiscal").map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Value">
                  {valueMetrics.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Context">
                  {contextMetrics.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label}
                    </option>
                  ))}
                </optgroup>
                <option value="off">Off</option>
              </select>
              {metricNote && choropleth !== "off" && (
                <p className="layer-meta">
                  {layerBusy ? "Loading…" : metricNote}
                </p>
              )}

              <div className="layer-chips">
                <button
                  type="button"
                  className={showBoundaries ? "chip active" : "chip"}
                  onClick={() => setShowBoundaries((v) => !v)}
                  title="Outlines of neighbouring pieces of land. Zoom in."
                >
                  Boundaries
                </button>
                <button
                  type="button"
                  className={showCellGrid ? "chip active" : "chip"}
                  onClick={() => setShowCellGrid((v) => !v)}
                  title="The small squares the estimate is built from. Zoom in."
                >
                  Cells
                </button>
                <button
                  type="button"
                  className={showMethod ? "chip active" : "chip"}
                  onClick={() => setShowMethod((v) => !v)}
                  title="Outline councils valued as farmland."
                >
                  Farmland councils
                </button>
              </div>
              {showVdl && (
                <p className="layer-meta">
                  SVDLS survey sites (OGL) — owner class is not a title. Zoom 8+.
                </p>
              )}
              {showPublicLand && (
                <div className="public-legend">
                  <p className="layer-meta">
                    Not a title. Not council land. Zoom 6+.
                  </p>
                  <ul className="public-legend-swatches">
                    <li>
                      <span className="swatch" style={{ background: "#66c2a5" }} />
                      Forestry and Land Scotland
                    </li>
                    <li>
                      <span className="swatch" style={{ background: "#8da0cb" }} />
                      NatureScot
                    </li>
                    <li>
                      <span className="swatch" style={{ background: "#e78ac3" }} />
                      Crown Estate
                    </li>
                    <li>
                      <span className="swatch" style={{ background: "#a6d854" }} />
                      Scottish Water
                    </li>
                    <li>
                      <span className="swatch" style={{ background: "#fc8d62" }} />
                      Crofting holdings
                    </li>
                  </ul>
                </div>
              )}
              {(coverageLive.length > 0 || coverageGaps.length > 0) && (
                <CoveragePanel
                  live={coverageLive}
                  gaps={coverageGaps}
                  open={coverageOpen}
                  onToggleOpen={() => setCoverageOpen((v) => !v)}
                  activeLayerIds={[
                    ...(showVdl ? ["vdl"] : []),
                    ...(showPublicLand ? ["public_crown"] : []),
                    ...(showBoundaries ? ["boundaries"] : []),
                    ...(showCellGrid ? ["cell_grid"] : []),
                  ]}
                  onToggleLayer={(id) => {
                    if (id === "vdl") setShowVdl((v) => !v);
                    if (id === "public_crown") setShowPublicLand((v) => !v);
                    if (id === "boundaries") setShowBoundaries((v) => !v);
                    if (id === "cell_grid") setShowCellGrid((v) => !v);
                  }}
                />
              )}

              <button
                type="button"
                className="hud-fold"
                onClick={() => setStatsOpen((v) => !v)}
              >
                {statsOpen ? "Hide national figures" : "Scotland figures"}
              </button>
              {statsOpen && (
                <div className="hud-stats">
                  {fiscalSummary?.enabled && (
                    <div
                      className={`fiscal-dash ${
                        fiscalSummary.revenue_neutral_or_better
                          ? "surplus"
                          : "shortfall"
                      }`}
                    >
                      <div className="fiscal-dash-title">
                        Research placeholder
                      </div>
                      <div className="fiscal-dash-grid">
                        <div>
                          <span className="fd-label">Placeholder list</span>
                          <span className="fd-value">
                            {formatBn(fiscalSummary.basket.total_gbp)}
                          </span>
                        </div>
                        <div>
                          <span className="fd-label">Illustrated charge</span>
                          <span className="fd-value">
                            {formatBn(fiscalSummary.collection.annual_gbp)}
                          </span>
                        </div>
                        <div>
                          <span className="fd-label">
                            {fiscalSummary.surplus_gbp >= 0
                              ? "Above the list"
                              : "Short of the list"}
                          </span>
                          <span className="fd-value">
                            {formatBn(Math.abs(fiscalSummary.surplus_gbp))}
                          </span>
                        </div>
                      </div>
                      <p className="fiscal-dash-note">
                        Research placeholder, not a rates bill and not
                        today&apos;s Scottish budget. One-person comparison{" "}
                        {formatGbp0(fiscalSummary.dividend.per_person_gbp)}
                      </p>
                    </div>
                  )}
                  <NationalStats />
                </div>
              )}
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
            {result && (
              <AgrBreakdown
                agr={result.agr}
                areaSqm={result.square.area_sqm}
                postcode={result.postcode?.postcode}
                doorLabel={addressLine}
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
                onDownloadReport={(fmt) => void downloadReport(fmt)}
                reportDownloading={reportDownloading}
              />
            )}
          </aside>
          )}
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

function legendCaption(id: MetricId): string {
  switch (id) {
    case "gross_liability":
    case "agr_plot":
      return "Town: a home plot. Rural: one hectare.";
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

function formatBn(n: number): string {
  return `£${(n / 1e9).toFixed(1)}bn`;
}

function formatGbp0(n: number): string {
  return `£${Math.round(n).toLocaleString("en-GB")}`;
}
