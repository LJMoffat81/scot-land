/**
 * GRID-BASE-1 runtime helpers for ScotlandMap — source/layer ids and paint.
 */

import type { Map as MaplibreMap } from "maplibre-gl";

import {
  EMPTY_FC,
  GRID3_HIGHLIGHT_FILL,
  GRID3_HIGHLIGHT_FILL_OPACITY,
  GRID3_HIGHLIGHT_HALO_WIDTH,
  GRID3_HIGHLIGHT_OUTLINE,
  GRID3_HIGHLIGHT_OUTLINE_WIDTH,
  GRID3_LAYER_HIGHLIGHT_FILL,
  GRID3_LAYER_HIGHLIGHT_HALO,
  GRID3_LAYER_HIGHLIGHT_LINE,
  GRID3_LAYER_LINES,
  GRID3_LAYER_LINES_HALO,
  GRID3_LINE_COLOR,
  GRID3_LINE_COLOR_IMAGERY,
  GRID3_LINE_HALO_COLOR,
  GRID3_LINE_OPACITY,
  GRID3_LINE_OPACITY_IMAGERY,
  GRID3_LINE_WIDTH,
  GRID3_SOURCE_HIGHLIGHT,
  GRID3_SOURCE_LINES,
} from "./grid3Map";

/** Ensure grid sources/layers exist below selected zone outline layers. */
export function ensureGrid3Layers(map: MaplibreMap): void {
  if (!map.getSource(GRID3_SOURCE_LINES)) {
    map.addSource(GRID3_SOURCE_LINES, { type: "geojson", data: EMPTY_FC });
  }
  if (!map.getSource(GRID3_SOURCE_HIGHLIGHT)) {
    map.addSource(GRID3_SOURCE_HIGHLIGHT, { type: "geojson", data: EMPTY_FC });
  }

  const beforeId = map.getLayer("selected-parcel-fill")
    ? "selected-parcel-fill"
    : map.getLayer("selected-square-fill")
      ? "selected-square-fill"
      : undefined;

  if (!map.getLayer(GRID3_LAYER_LINES_HALO)) {
    map.addLayer(
      {
        id: GRID3_LAYER_LINES_HALO,
        type: "line",
        source: GRID3_SOURCE_LINES,
        layout: { visibility: "none" },
        paint: {
          "line-color": GRID3_LINE_HALO_COLOR,
          "line-width": GRID3_LINE_WIDTH + 1,
          "line-opacity": 0.55,
        },
      },
      beforeId,
    );
  }
  if (!map.getLayer(GRID3_LAYER_LINES)) {
    map.addLayer(
      {
        id: GRID3_LAYER_LINES,
        type: "line",
        source: GRID3_SOURCE_LINES,
        layout: { visibility: "none" },
        paint: {
          "line-color": GRID3_LINE_COLOR,
          "line-width": GRID3_LINE_WIDTH,
          "line-opacity": GRID3_LINE_OPACITY,
        },
      },
      beforeId,
    );
  }
  if (!map.getLayer(GRID3_LAYER_HIGHLIGHT_FILL)) {
    map.addLayer(
      {
        id: GRID3_LAYER_HIGHLIGHT_FILL,
        type: "fill",
        source: GRID3_SOURCE_HIGHLIGHT,
        layout: { visibility: "none" },
        paint: {
          "fill-color": GRID3_HIGHLIGHT_FILL,
          "fill-opacity": GRID3_HIGHLIGHT_FILL_OPACITY,
        },
      },
      beforeId,
    );
  }
  if (!map.getLayer(GRID3_LAYER_HIGHLIGHT_HALO)) {
    map.addLayer(
      {
        id: GRID3_LAYER_HIGHLIGHT_HALO,
        type: "line",
        source: GRID3_SOURCE_HIGHLIGHT,
        layout: { visibility: "none" },
        paint: {
          "line-color": "#ffffff",
          "line-width":
            GRID3_HIGHLIGHT_OUTLINE_WIDTH + GRID3_HIGHLIGHT_HALO_WIDTH * 2,
          "line-opacity": 0.95,
        },
      },
      beforeId,
    );
  }
  if (!map.getLayer(GRID3_LAYER_HIGHLIGHT_LINE)) {
    map.addLayer(
      {
        id: GRID3_LAYER_HIGHLIGHT_LINE,
        type: "line",
        source: GRID3_SOURCE_HIGHLIGHT,
        layout: { visibility: "none" },
        paint: {
          "line-color": GRID3_HIGHLIGHT_OUTLINE,
          "line-width": GRID3_HIGHLIGHT_OUTLINE_WIDTH,
          "line-opacity": 0.95,
        },
      },
      beforeId,
    );
  }

  // G19 — selected zone outline always above grid hover/highlight.
  for (const id of [
    "selected-parcel-fill",
    "selected-parcel-outline",
    "selected-square-fill",
    "selected-square-outline",
  ]) {
    if (map.getLayer(id)) {
      try {
        map.moveLayer(id);
      } catch {
        /* ignore */
      }
    }
  }
}

export function setGrid3LinePaint(
  map: MaplibreMap,
  imagery: boolean,
): void {
  if (!map.getLayer(GRID3_LAYER_LINES)) return;
  if (imagery) {
    map.setPaintProperty(
      GRID3_LAYER_LINES,
      "line-color",
      GRID3_LINE_COLOR_IMAGERY,
    );
    map.setPaintProperty(
      GRID3_LAYER_LINES,
      "line-opacity",
      GRID3_LINE_OPACITY_IMAGERY,
    );
    if (map.getLayer(GRID3_LAYER_LINES_HALO)) {
      map.setLayoutProperty(GRID3_LAYER_LINES_HALO, "visibility", "visible");
    }
  } else {
    map.setPaintProperty(GRID3_LAYER_LINES, "line-color", GRID3_LINE_COLOR);
    map.setPaintProperty(
      GRID3_LAYER_LINES,
      "line-opacity",
      GRID3_LINE_OPACITY,
    );
    if (map.getLayer(GRID3_LAYER_LINES_HALO)) {
      map.setLayoutProperty(GRID3_LAYER_LINES_HALO, "visibility", "none");
    }
  }
}

export function setGrid3Visibility(
  map: MaplibreMap,
  linesOn: boolean,
  highlightOn: boolean,
): void {
  const lineVis = linesOn ? "visible" : "none";
  const hiVis = highlightOn ? "visible" : "none";
  for (const id of [GRID3_LAYER_LINES]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", lineVis);
  }
  // Halo only when imagery paint enables it separately.
  for (const id of [
    GRID3_LAYER_HIGHLIGHT_FILL,
    GRID3_LAYER_HIGHLIGHT_HALO,
    GRID3_LAYER_HIGHLIGHT_LINE,
  ]) {
    if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", hiVis);
  }
}
