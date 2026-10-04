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
import {
  SERVICE_BUSY,
  apiFetch,
  apiJson,
  isServiceFailure,
  pingApi,
  visitorFacingError,
} from "../lib/api";
import { CONTEXT_GROUPS, CONTEXT_LAYERS } from "../lib/contextLayers";

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

export default function ScotlandMap() {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const lookupGen = useRef(0);
  const [mapReady, setMapReady] = useState(false);
  const [query, setQuery] = useState("");
  const [placeMatches, setPlaceMatches] = useState<PlaceMatch[] | null>(null);
  const [addressLine, setAddressLine] = useState<string | null>(null);
  const [scenario, setScenario] = useState<ScenarioId>("full_agr");
  const [choropleth, setChoropleth] = useState<MetricId | "off">("gross_liability");
  const [showBoundaries, setShowBoundaries] = useState(false);
  const [showCellGrid] = useState(false);
  const [showVdl, setShowVdl] = useState(false);
  const [showPublicLand, setShowPublicLand] = useState(false);
  const [showMethod, setShowMethod] = useState(false);
  const [contextOn, setContextOn] = useState<Record<string, boolean>>({});
  const [urbanRuralName, setUrbanRuralName] = useState<string | null>(null);
  const [contextNote, setContextNote] = useState<string | null>(null);
  const contextLoaded = useRef<Set<string>>(new Set());
  const contextFlight = useRef<Set<string>>(new Set());
  const [layerBusy, setLayerBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SquareResponse | null>(null);
  const [apiOk, setApiOk] = useState<boolean | null>(null);
  const [metricNote, setMetricNote] = useState<string | null>(null);
  const [activeStory, setActiveStory] = useState<StoryId>("who_pays");
  const [band, setBand] = useState<RentBand | null>(null);
  const [streetScale, setStreetScale] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [mapStyle, setMapStyle] = useState<"streets" | "satellite">("streets");
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
    setScenario(payload.agr.active_scenario);

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
      const area = payload.agr.parcel_area_sqm;
      const yearly = parcelYearlyRent(payload);
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
      if (!keepLabel) {
        setPlaceMatches(null);
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
    setPlaceMatches(null);
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

  const openPostcode = async (postcode: string, generation: number) => {
    const response = await apiFetch(
      `/postcode/${encodeURIComponent(postcode)}?scenario=${scenario}`,
    );
    const payload = (await response.json()) as SquareResponse;
    if (generation !== lookupGen.current) return;
    setPlaceMatches(null);
    setAddressLine(null);
    applyResult(payload);
  };

  const openWords = async (words: string, generation: number) => {
    const response = await apiFetch(
      `/square?words=${encodeURIComponent(words)}&scenario=${scenario}`,
    );
    const payload = (await response.json()) as SquareResponse;
    if (generation !== lookupGen.current) return;
    setPlaceMatches(null);
    setAddressLine(null);
    applyResult(payload);
  };

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    const generation = ++lookupGen.current;
    setLoading(true);
    setError(null);
    setPlaceMatches(null);
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
        setPlaceMatches(body.matches);
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

  const pickPlace = (match: PlaceMatch) => {
    const generation = ++lookupGen.current;
    setPlaceMatches(null);
    setAddressLine(match.label);
    setError(null);
    void fetchSquare(match.lat, match.lng, undefined, true, generation);
  };

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
      center: [-4.2, 56.8],
      zoom: 6.2,
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    map.getCanvas().style.cursor = "pointer";

    let seenWidth = -1;
    let seenHeight = -1;
    const resizeObserver = new ResizeObserver(() => {
      const nextWidth = container.clientWidth;
      const nextHeight = container.clientHeight;
      if (nextWidth === seenWidth && nextHeight === seenHeight) return;
      seenWidth = nextWidth;
      seenHeight = nextHeight;
      map.resize();
    });
    resizeObserver.observe(container);

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
            setError(visitorFacingError(err));
            if (isServiceFailure(err)) {
              void pingApi().then((s) => setApiOk(s.ok));
            }
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
      resizeObserver.disconnect();
      markerRef.current?.remove();
      markerRef.current = null;
      parcelLabelRef.current?.remove();
      parcelLabelRef.current = null;
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
    if (!map) return;
    const sync = () => {
      const close = map.getZoom() >= 14;
      setStreetScale(close);
      if (boundariesTouched.current || map.isMoving()) return;
      setShowBoundaries(close);
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
      showBoundaries ? "visible" : "none",
    );
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
  }, [mapReady, contextOn]);

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
    if (!mapReady) return;
    const map = mapRef.current;
    if (!map?.getLayer("council-method")) return;
    map.setLayoutProperty(
      "council-method",
      "visibility",
      showMethod && choropleth !== "off" && !streetScale ? "visible" : "none",
    );
  }, [mapReady, showMethod, choropleth, streetScale]);

  const legendMetric =
    choropleth === "off"
      ? null
      : (METRICS.find((m) => m.id === choropleth) ?? null);

  return (
    <div className={toolsOpen ? "app-shell tools-open" : "app-shell"}>
      <div className="map-stage">
      <div className="map-wrap">
        <div id="map" ref={mapContainer} />
        {!result && apiOk !== false && (
          <div className="map-hint">Click a place for its Annual Ground Rent</div>
        )}
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
              ? placeMatches && placeMatches.length > 1
                ? "hud-search has-results loading"
                : "hud-search loading"
              : placeMatches && placeMatches.length > 1
                ? "hud-search has-results"
                : "hud-search"
          }
        >
          <label className="sr-only" htmlFor="place-query">
            Postcode, address, or title number
          </label>
          <input
            id="place-query"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void runSearch();
            }}
            placeholder="Postcode, address, or title number"
          />
          <button
            type="button"
            className="hud-search-go"
            disabled={!query.trim()}
            onClick={() => void runSearch()}
          >
            {loading ? "…" : "Search"}
          </button>
          {placeMatches && placeMatches.length > 1 && (
            <ul className="door-matches">
              {placeMatches.map((match) => (
                <li key={`${match.lat},${match.lng},${match.label}`}>
                  <button type="button" onClick={() => pickPlace(match)}>
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

      <aside className="hud-scotland" aria-label="Land rent" ref={scotlandRef}>
        <input
          id="legend-fold"
          type="checkbox"
          className="hud-scotland-fold-input"
        />
        <div className="hud-scotland-stack">
          <label className="hud-scotland-fold" htmlFor="legend-fold">
            <span className="hud-scotland-fold-show">Show legend</span>
            <span className="hud-scotland-fold-hide">Hide legend</span>
          </label>
          <div className="hud-scotland-body">
            <p className="hud-scotland-job">Annual Ground Rent</p>
            <p className="hud-scotland-lead">A charge on the land alone.</p>
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
                {(choropleth === "gross_liability" ||
                  choropleth === "agr_plot" ||
                  choropleth === "rent_per_sqm") && (
                  <p className="hud-scotland-note">
                    The colour is one rate for the whole council, the same from street
                    to street.
                  </p>
                )}
              </div>
            )}
            <p className="hud-scotland-foot">
              Research estimate, not a rates bill. <a href="/methodology">About</a>
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
                {(["low", "mid", "high"] as RentBand[]).map((id) => (
                  <button
                    key={id}
                    type="button"
                    className={band === id ? "chip active" : "chip"}
                    onClick={() => setBand((cur) => (cur === id ? null : id))}
                    title="Low is under £1,500 a year. High is £4,500 or more."
                  >
                    {id} rent
                  </button>
                ))}
              </div>
              {band && (
                <p className="layer-meta">Showing {band} rent councils.</p>
              )}
              {metricNote && choropleth !== "off" && (
                <p className="layer-meta">
                  {layerBusy ? "Loading…" : metricNote}
                </p>
              )}

              <div className="layer-chips">
                <button
                  type="button"
                  className={showBoundaries ? "chip active" : "chip"}
                  onClick={() => {
                    boundariesTouched.current = true;
                    setShowBoundaries((v) => !v);
                  }}
                  title="Outlines of neighbouring pieces of land. Zoom in."
                >
                  Boundaries
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
              {CONTEXT_GROUPS.map((group) => (
                <div key={group}>
                  <label className="layer-select-label">{group}</label>
                  <div className="layer-chips">
                    {CONTEXT_LAYERS.filter((layer) => layer.group === group).map(
                      (layer) => (
                        <button
                          key={layer.id}
                          type="button"
                          className={contextOn[layer.id] ? "chip active" : "chip"}
                          title={layer.title}
                          onClick={() =>
                            setContextOn((cur) => ({
                              ...cur,
                              [layer.id]: !cur[layer.id],
                            }))
                          }
                        >
                          {layer.label}
                        </button>
                      ),
                    )}
                    {group === "Use" && (
                      <>
                        <button
                          type="button"
                          className={showVdl ? "chip active" : "chip"}
                          title="Surveyed vacant and derelict land. A use, not a rent."
                          onClick={() => setShowVdl((on) => !on)}
                        >
                          Vacant and derelict
                        </button>
                        <button
                          type="button"
                          className={showPublicLand ? "chip active" : "chip"}
                          title="Five public and Crown holdings. Not a title and not a unique rent."
                          onClick={() => setShowPublicLand((on) => !on)}
                        >
                          Public and Crown
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {CONTEXT_LAYERS.filter((layer) => contextOn[layer.id]).map((layer) => (
                <p key={layer.id} className="layer-meta">
                  {layer.attribution}
                </p>
              ))}
              {showVdl && (
                <p className="layer-meta">
                  Scottish Vacant and Derelict Land Survey. Contains public
                  sector information licensed under the Open Government Licence
                  v3.0. Survey polygons, not a title.
                </p>
              )}
              {showPublicLand && (
                <p className="layer-meta">
                  Scottish Public and Crown Estate Land 2024. Five bodies only,
                  not a title and not a unique rent.
                </p>
              )}
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
            {result && (
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


