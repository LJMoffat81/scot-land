
import { test, expect, routeManifestOverride } from "./_fixtures";
import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean, ensureLayersGroupOpen, ensureMapZoomAtLeast, openLayers, openMap, stubMapCardsBackend, getVisibleLayerIds, waitForMap } from "./_mapCardsHelpers";
import {
  defaultOnLayerIds,
  getMapLayer,
  LDP_HIGHLAND_COVERAGE_NOTE,
} from "../../lib/mapLayerRegistry";
import { parseTileManifest } from "../../lib/tileLayerFactory";
import {
  buildMapAttributionPieces,
  shortLayerSourceName,
} from "../../lib/mapAttributionLine";
import { LAYERS_ADD_WAITING } from "../../lib/layersAddRegistry";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * LAYERS-ADD-1 — registry rows default OFF; LDP/HLS on roadmap; no £; banned names.
 * PLANNING-PUBLISH-1 PR-B (PB-*) — hls-open / ldp-highland rows, synthetic manifest only.
 *   Since PR-B only LDP stays on the roadmap (Highland is live); HLS is on the map.
 * Accordion groups must be expanded before toggles exist in the DOM (MAP-CARDS).
 * Improvement Service rows are omitted when the extract is absent.
 */

const NEW_OFF_BY_GROUP: Record<string, readonly string[]> = {
  land: ["access_services"],
  places: [],
};

/** LAYERS-FIX-1: empty stubs are not switches. */
const HIDDEN_STUBS = [
  "flood",
  "deprivation",
  "conservation",
  "listed",
  "stops",
] as const;

const ABSENT_IS = ["contaminated_land", "green_belt", "school_catchments"] as const;

/** Visible new rows, and the map layer each toggle must draw. */
const DRAWN_ROWS = [
  { toggle: "access_services", layer: "access_services-add-fill" },
] as const;

const PRESENT_IS_ROWS = [
  { toggle: "contaminated_land", layer: "contaminated_land-add-fill" },
  { toggle: "green_belt", layer: "green_belt-add-fill" },
  { toggle: "school_catchments", layer: "school_catchments-add-fill" },
] as const;

async function stubViewportShapes(page: Page) {
  await page.route("**/layers/add/viewport/**", async (route) => {
    const url = new URL(route.request().url());
    const south = Number(url.searchParams.get("south"));
    const west = Number(url.searchParams.get("west"));
    const north = Number(url.searchParams.get("north"));
    const east = Number(url.searchParams.get("east"));
    const lngPad = (east - west) * 0.15;
    const latPad = (north - south) * 0.15;
    const body = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: {
            stop_type: "bus",
            category: "A",
            name: "Town centre",
            q: 1,
            topic: "access",
            class: "1",
          },
          geometry: {
            type: "Polygon",
            coordinates: [
              [
                [west + lngPad, south + latPad],
                [east - lngPad, south + latPad],
                [east - lngPad, north - latPad],
                [west + lngPad, north - latPad],
                [west + lngPad, south + latPad],
              ],
            ],
          },
        },
        {
          type: "Feature",
          properties: { stop_type: "bus", category: "A" },
          geometry: {
            type: "Point",
            coordinates: [(west + east) / 2, (south + north) / 2],
          },
        },
      ],
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

async function expectLayerDrawn(page: Page, layerId: string) {
  await expect
    .poll(
      async () =>
        page.evaluate((id) => {
          const map = (
            window as unknown as {
              __map?: {
                getLayer(layer: string): unknown;
                queryRenderedFeatures(opts: { layers: string[] }): unknown[];
              };
            }
          ).__map;
          if (!map?.getLayer(id)) return 0;
          return map.queryRenderedFeatures({ layers: [id] }).length;
        }, layerId),
      { timeout: 20_000 },
    )
    .toBeGreaterThan(0);
}

for (const width of [1280, 390] as const) {
  test.describe(`LAYERS-ADD-1 @ ${width}`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } });

    test("new layers default off; gated ids absent; roadmap waiting rows", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      for (const key of ["land", "places"] as const) {
        await ensureLayersGroupOpen(page, key);
        for (const id of NEW_OFF_BY_GROUP[key]!) {
          const toggle = page.getByTestId(`layer-toggle-${id}`);
          await expect(toggle).toBeVisible();
          await expect(toggle).toHaveAttribute("aria-checked", "false");
        }
      }

      for (const id of HIDDEN_STUBS) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
      }

      for (const id of ABSENT_IS) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
      }

      await expect(page.getByTestId("layer-toggle-hla")).toHaveCount(0);
      await expect(page.getByTestId("layer-toggle-ldp")).toHaveCount(0);
      const panel = page.getByTestId("layers-panel");
      // CLEANUP-318 (from e2e/hla-not-loaded.spec.ts): legacy HLA overlay copy stays off the panel.
      await expect(panel).not.toContainText("Housing land audit");
      await expect(panel).not.toContainText(/£/);
      await expect(panel).not.toContainText(/\bSIMD\b/);
      await expect(panel).not.toContainText(/\bNaPTAN\b/);

      await page.goto("/roadmap#map-layers");
      await expect(page.getByTestId("roadmap-waiting-ldp")).toBeVisible();
      // PLANNING-PUBLISH-1 PR-B: hls is on the map; ldp is Highland only.
      await expect(page.getByTestId("roadmap-waiting-hls")).toHaveCount(0);
      await expect(page.getByTestId("roadmap-waiting-status-ldp")).toContainText(
        "On the map for Highland only. For other councils, we're waiting for permission to use the data.",
      );
      await expect(page.locator("main")).not.toContainText(/£/);
      await expect(page.locator("main")).not.toContainText(/sepa_frm_maps/i);

      assertConsoleClean(gate);
    });
  });
}

test.describe("LAYERS-ADD-1 paint", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("toggling each new row draws; absent IS layers stay off the list", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await stubViewportShapes(page);
    await openMap(page);
    await expect
      .poll(async () => page.locator("#map").getAttribute("data-framed"))
      .toBe("1");
    await ensureMapZoomAtLeast(page, 15);
    await openLayers(page);

    for (const id of ABSENT_IS) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
    }
    for (const id of HIDDEN_STUBS) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
    }

    for (const row of DRAWN_ROWS) {
      const group = row.toggle === "access_services" ? "land" : "places";
      await ensureLayersGroupOpen(page, group);
      await page.getByTestId(`layer-toggle-${row.toggle}`).click();
      await expectLayerDrawn(page, row.layer);
    }

    assertConsoleClean(gate);
  });

  test("present Improvement Service rows draw", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page, {
      spatialHubLayerIds: ["vdl", ...PRESENT_IS_ROWS.map((row) => row.toggle)],
    });
    await stubViewportShapes(page);
    await openMap(page);
    await expect
      .poll(async () => page.locator("#map").getAttribute("data-framed"))
      .toBe("1");
    await ensureMapZoomAtLeast(page, 15);
    await openLayers(page);

    for (const row of PRESENT_IS_ROWS) {
      const group =
        row.toggle === "contaminated_land" ? "limits" : "places";
      await ensureLayersGroupOpen(page, group);
      const toggle = page.getByTestId(`layer-toggle-${row.toggle}`);
      await expect(toggle).toBeVisible();
      await toggle.click();
      await expectLayerDrawn(page, row.layer);
    }

    assertConsoleClean(gate);
  });
});

// ---- PLANNING-PUBLISH-1 PR-B ----

const HLS_LEGEND = "Housing land supply site (open data)";
const LDP_LEGEND = "Local Development Plan allocation (Highland only)";

function entry(id: string, over: Record<string, unknown> = {}) {
  return {
    layer: id,
    version: "2026-10-06.abcdef12",
    minzoom: 0,
    maxzoom: 14,
    geometry: "polygon",
    source_layer: id,
    measure: null,
    attribution: `SYNTH ${id} CREDIT`,
    vintage: `SYNTH ${id} VINTAGE`,
    style: {
      fill: { "fill-color": "#6a7f2a", "fill-opacity": 0.3 },
      line: { "line-color": "#6a7f2a", "line-width": 1.2, "line-opacity": 0.9 },
    },
    legend: [
      { label: id === "hls-open" ? HLS_LEGEND : LDP_LEGEND, color: "#6a7f2a" },
    ],
    ...over,
  };
}

async function serveManifest(page: Page, tilesets: Record<string, unknown>) {
  await routeManifestOverride(page, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ schema: 1, tilesets }),
    });
  });
  await page.route("**/backend/v1/tiles/**/*.mvt", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
}

async function openDrawer(page: Page) {
  await openMap(page, "/?z=7&c=-4.5,57.3");
  await waitForMap(page);
  await openLayers(page);
  await ensureLayersGroupOpen(page, "land");
}

test("PB-U1 registry: both rows default off; default set unchanged", () => {
  expect(getMapLayer("hls-open")?.defaultOn).toBe(false);
  expect(getMapLayer("ldp-highland")?.defaultOn).toBe(false);
  expect(defaultOnLayerIds()).toEqual(["data_zones"]);
  expect(getMapLayer("ldp-highland")?.legendNote).toBe(LDP_HIGHLAND_COVERAGE_NOTE);
  // PL Q3: the HLS gap is never silent (exact text, WUX-locked 17:06 GMT).
  expect(getMapLayer("hls-open")?.legendNote).toBe(
    "North Lanarkshire is not shown, because the council's licence allows its housing land supply data to be viewed but not republished.",
  );
});

test("PB-U2 manifest vintage and attribution fail closed", () => {
  const ok = parseTileManifest({ schema: 1, tilesets: { "hls-open": entry("hls-open") } });
  expect(ok.tilesets["hls-open"].vintage).toBe("SYNTH hls-open VINTAGE");
  // Live §14 LDP vintage (13 Nov 2026) must pass the guard unchanged.
  const ldpVintage = "Highland Council live data, last updated 19 Aug 2025";
  const live = parseTileManifest({
    schema: 1,
    tilesets: { "ldp-highland": entry("ldp-highland", { vintage: ldpVintage }) },
  });
  expect(live.tilesets["ldp-highland"].vintage).toBe(ldpVintage);
  for (const bad of ["", "  ", 12, true, [], {}, "as at {date}"]) {
    expect(() =>
      parseTileManifest({
        schema: 1,
        tilesets: { "hls-open": entry("hls-open", { vintage: bad }) },
      }),
    ).toThrowError(/^manifest: bad vintage hls-open$/);
  }
  for (const bad of ["", null, undefined, 7]) {
    expect(() =>
      parseTileManifest({
        schema: 1,
        tilesets: { "ldp-highland": entry("ldp-highland", { attribution: bad }) },
      }),
    ).toThrowError(/^manifest: bad attribution ldp-highland$/);
  }
});

test("PB-U3 credit is manifest-only (no hard-coded fallback)", () => {
  expect(buildMapAttributionPieces(["hls-open", "ldp-highland"], {})).toEqual(
    buildMapAttributionPieces([], {}),
  );
  const pieces = buildMapAttributionPieces(["hls-open"], {
    "hls-open": "SYNTH hls-open CREDIT",
  });
  expect(pieces.filter((p) => p.id === "hls-open")).toEqual([
    { id: "hls-open", text: "SYNTH hls-open CREDIT" },
  ]);
});

test("PB-E1 rows default off; toggle shows manifest legend, vintage, credit", async ({
  page,
  gate,
}) => {
  test.setTimeout(120_000);
  attachConsoleGate(page);
  await stubMapCardsBackend(page);
  await serveManifest(page, {
    "hls-open": entry("hls-open"),
    "ldp-highland": entry("ldp-highland"),
  });
  await openDrawer(page);

  for (const id of ["hls-open", "ldp-highland"]) {
    await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveAttribute(
      "aria-checked",
      "false",
    );
  }
  await expect(page.getByTestId("layer-toggle-data_zones")).toHaveAttribute(
    "aria-checked",
    "true",
  );
  let visible = await getVisibleLayerIds(page);
  expect(visible.filter((id) => /hls-open|ldp-highland/.test(id))).toEqual([]);
  await expect(page.getByTestId("map-attribution-line")).not.toContainText("SYNTH");

  await page.getByTestId("layer-toggle-hls-open").click();
  const hlsLegend = page.getByTestId("layer-inline-legend-hls-open");
  await expect(hlsLegend).toContainText(HLS_LEGEND);
  await expect(hlsLegend.getByTestId("layer-legend-note-hls-open")).toHaveText(
    "North Lanarkshire is not shown, because the council's licence allows its housing land supply data to be viewed but not republished.",
  );
  await page.getByTestId("layer-toggle-hls-open").click();
  await expect(page.getByTestId("layer-toggle-hls-open")).toHaveAttribute(
    "aria-checked",
    "false",
  );

  await page.getByTestId("layer-toggle-ldp-highland").click();
  const legend = page.getByTestId("layer-inline-legend-ldp-highland");
  await expect(legend).toContainText(LDP_LEGEND);
  await expect(legend.getByTestId("layer-legend-note-ldp-highland")).toHaveText(
    "Highland Council area only. The part inside Cairngorms National Park is not shown, because the Cairngorms National Park Authority prepares the plan there.",
  );
  await expect(page.getByTestId("layer-vintage-ldp-highland")).toHaveText(
    "SYNTH ldp-highland VINTAGE",
  );
  await expect(page.getByTestId("map-attribution-line")).toContainText(
    "SYNTH ldp-highland CREDIT",
  );
  await expect
    .poll(async () =>
      (await getVisibleLayerIds(page)).filter((id) => /hls-open|ldp-highland/.test(id)),
    )
    .toEqual(["tile-ldp-highland-fill", "tile-ldp-highland-line"]);
  assertConsoleClean(gate);
});

test("PB-N1 gated (absent from manifest) row is hidden, other row still works", async ({
  page,
  gate,
}) => {
  test.setTimeout(120_000);
  attachConsoleGate(page);
  await stubMapCardsBackend(page);
  await serveManifest(page, { "ldp-highland": entry("ldp-highland") });
  await openDrawer(page);
  await expect(page.getByTestId("layer-toggle-ldp-highland")).toHaveCount(1);
  await expect(page.getByTestId("layer-toggle-hls-open")).toHaveCount(0);
  assertConsoleClean(gate);
});

for (const [name, over] of [
  ["PB-N2 missing credit", { attribution: "" }],
  ["PB-N3 templated vintage", { vintage: "as at {date}" }],
] as const) {
  test(`${name} fails the manifest closed; rows hidden`, async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await serveManifest(page, {
      "hls-open": entry("hls-open", over),
      "ldp-highland": entry("ldp-highland"),
    });
    await openDrawer(page);
    await expect(page.getByTestId("layer-notice")).toHaveText("One layer did not load.");
    await expect(page.getByTestId("layer-toggle-hls-open")).toHaveCount(0);
    await expect(page.getByTestId("layer-toggle-ldp-highland")).toHaveCount(0);
    assertConsoleClean(gate);
  });
}

// ---- CLEANUP-318: exact copy pins (PR-B strings 1-9, 11; WUX-locked 13 Nov 2026) ----

const C318_COPY = {
  hlsLabel: "Housing land supply sites",
  hlsSubline:
    "Sites where councils expect new homes to be built. This shows planning supply, not land value or ownership.",
  hlsCaption: "Improvement Service Spatial Hub · open data",
  ldpLabel: "Local Development Plan allocations (Highland only)",
  ldpSubline:
    "Land the Highland Local Development Plan allocates for a specific use. This is a planning designation, not land value or ownership.",
  ldpCaption: "The Highland Council · open data",
  ldpNote:
    "Highland Council area only. The part inside Cairngorms National Park is not shown, because the Cairngorms National Park Authority prepares the plan there.",
  hlsCredit: "Housing land supply: Improvement Service",
  ldpCredit: "Highland development plan: The Highland Council",
  ldpStatusShort: "Highland only so far",
} as const;

test("C318-U1 registry, credit and roadmap copy are exact literals", () => {
  const hls = getMapLayer("hls-open");
  const ldp = getMapLayer("ldp-highland");
  expect(hls?.label).toBe(C318_COPY.hlsLabel);
  expect(hls?.subline).toBe(C318_COPY.hlsSubline);
  expect(hls?.sourceCaption).toBe(C318_COPY.hlsCaption);
  expect(ldp?.label).toBe(C318_COPY.ldpLabel);
  expect(ldp?.subline).toBe(C318_COPY.ldpSubline);
  expect(ldp?.sourceCaption).toBe(C318_COPY.ldpCaption);
  expect(ldp?.legendNote).toBe(C318_COPY.ldpNote);
  expect(shortLayerSourceName({ id: "hls-open", text: "x" })).toBe(C318_COPY.hlsCredit);
  expect(shortLayerSourceName({ id: "ldp-highland", text: "x" })).toBe(C318_COPY.ldpCredit);
  expect(LAYERS_ADD_WAITING.map((row) => row.id)).toEqual(["ldp"]);
  expect(LAYERS_ADD_WAITING[0].statusShort).toBe(C318_COPY.ldpStatusShort);
  // Checked-on label: live feed only; every other row keeps "Data as of".
  expect(ldp?.asOfLabel).toBe("Checked on");
  expect(ldp?.extractAsOf).toBeUndefined();
  // hls-open: fixed extract date from the registry (never the tile build date).
  expect(hls?.extractAsOf).toBe("6 Oct 2026");
  expect(hls?.asOfLabel).toBeUndefined();
});

// Live manifest versions on 13 Nov 2026: both rebuilt that day. The version date is
// run_layer's fetch date (as_of), i.e. when we last pulled the source.
const C318_LIVE_VERSIONS = {
  "hls-open": "2026-11-13.0dcf8d9c",
  "ldp-highland": "2026-11-13.006d7e43",
} as const;

test("C318-E1 drawer shows exact copy; coverage notes sit under the key; Checked on", async ({
  page,
  gate,
}) => {
  test.setTimeout(120_000);
  attachConsoleGate(page);
  await stubMapCardsBackend(page);
  await serveManifest(page, {
    "hls-open": entry("hls-open", { version: C318_LIVE_VERSIONS["hls-open"] }),
    "ldp-highland": entry("ldp-highland", {
      version: C318_LIVE_VERSIONS["ldp-highland"],
    }),
  });
  await openDrawer(page);

  await expect(page.getByTestId("layer-toggle-hls-open")).toHaveText(C318_COPY.hlsLabel);
  await expect(page.getByTestId("layer-desc-hls-open")).toHaveText(C318_COPY.hlsSubline);
  await expect(page.getByTestId("layer-toggle-ldp-highland")).toHaveText(C318_COPY.ldpLabel);
  await expect(page.getByTestId("layer-desc-ldp-highland")).toHaveText(C318_COPY.ldpSubline);

  for (const id of ["hls-open", "ldp-highland"] as const) {
    await page.getByTestId(`layer-toggle-${id}`).click();
    const legend = page.getByTestId(`layer-inline-legend-${id}`);
    // The coverage note follows the colour key (WUX nit 4).
    const noteAfterKey = await legend.evaluate((root, noteId) => {
      const key = root.querySelector("ul.layer-legend");
      const note = root.querySelector(`[data-testid="${noteId}"]`);
      if (!key || !note) return "missing";
      return key.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING
        ? "after"
        : "before";
    }, `layer-legend-note-${id}`);
    expect(noteAfterKey).toBe("after");
  }
  // hls-open: fixed extract date, although its tiles were rebuilt on 13 Nov 2026.
  await expect(page.getByTestId("layer-source-caption-hls-open")).toHaveText(
    "Improvement Service Spatial Hub · open data · Data as of 6 Oct 2026",
  );
  await expect(page.getByTestId("layer-asof-hls-open")).toHaveText(
    " · Data as of 6 Oct 2026",
  );
  // ldp-highland is a live feed: the date we last pulled it (manifest version date).
  await expect(page.getByTestId("layer-source-caption-ldp-highland")).toHaveText(
    "The Highland Council · open data · Checked on 13 Nov 2026",
  );
  await expect(page.getByTestId("layer-asof-ldp-highland")).toHaveText(
    " · Checked on 13 Nov 2026",
  );
  await expect(page.getByTestId("layer-legend-note-ldp-highland")).toHaveText(
    C318_COPY.ldpNote,
  );
  await expect(page.getByTestId("layer-flood-extent-legend")).toHaveCount(0);
  assertConsoleClean(gate);
});

test("C318-E2 roadmap short status is exact", async ({ page }) => {
  await stubMapCardsBackend(page);
  await page.goto("/roadmap#map-layers");
  await expect(
    page.getByTestId("roadmap-waiting-status-ldp").locator(".roadmap-waiting-status-short"),
  ).toHaveText(C318_COPY.ldpStatusShort);
});

for (const width of [360, 390] as const) {
  test(`C318-E3 @ ${width} Checked on caption wraps in full (no truncation)`, async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width, height: 844 });
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    // Single-digit day pins the format: no leading zero, 3-letter month, no full stop.
    await serveManifest(page, {
      "ldp-highland": entry("ldp-highland", { version: "2026-11-03.006d7e43" }),
    });
    await openDrawer(page);
    await page.getByTestId("layer-toggle-ldp-highland").click();
    const caption = page.getByTestId("layer-source-caption-ldp-highland");
    await caption.scrollIntoViewIfNeeded();
    await expect(caption).toBeVisible();
    await expect(caption).toHaveText(
      "The Highland Council · open data · Checked on 3 Nov 2026",
    );
    const box = await caption.evaluate((el) => {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return {
        overflowX: el.scrollWidth - el.clientWidth,
        textOverflow: cs.textOverflow,
        whiteSpace: cs.whiteSpace,
        right: r.right,
        vw: window.innerWidth,
      };
    });
    expect(box.textOverflow).not.toBe("ellipsis");
    expect(box.whiteSpace).not.toBe("nowrap");
    expect(box.overflowX).toBeLessThanOrEqual(0);
    expect(box.right).toBeLessThanOrEqual(box.vw);
    assertConsoleClean(gate);
  });
}
