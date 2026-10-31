/**
 * SEA-EXTENT-2 — permanent Scotland land-and-waters outline (frontend).
 * SE-U1/U2 pure; SE-E1–E4 e2e. Manifest only via routeManifestOverride.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, routeManifestOverride } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  readCreditShortNames,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import type { Page } from "@playwright/test";
import {
  CONTEXT_LAYERS,
  TILE_LAYER_IDS_ORDERED,
} from "../../lib/contextLayers";
import {
  SCOTLAND_EXTENT_CREDIT,
  buildMapAttributionPieces,
  shortLayerSourceName,
} from "../../lib/mapAttributionLine";

registerOpenFreeMapFontStub();

const ARCH2B = join(process.cwd(), "e2e", "fixtures", "arch2b");
const SEA = join(process.cwd(), "e2e", "fixtures", "sea-extent-2");
const VERSION = "2026-10-22.d28ecc72";

const MVT: Record<string, Buffer> = {
  dz2022: readFileSync(join(ARCH2B, "dz2022.mvt")),
  "oil-fields": readFileSync(join(ARCH2B, "oil-fields.mvt")),
  platforms: readFileSync(join(ARCH2B, "platforms.mvt")),
  pipelines: readFileSync(join(ARCH2B, "pipelines.mvt")),
  "scotland-extent": readFileSync(join(SEA, "scotland-extent.mvt")),
};

const SHORT_OUTLINE = "Scotland outline: UKHO / OS";

function arch2bTilesets() {
  return {
    dz2022: {
      layer: "dz2022",
      version: VERSION,
      minzoom: 0,
      maxzoom: 14,
      geometry: "polygon" as const,
      title: "Data Zones 2022",
      source_layer: "dz2022",
      measure: "pop_density",
      attribution: "Synthetic DZ attribution",
      style: {
        fill: {
          "fill-color": "#d9d9d9",
          "fill-opacity": 0.55,
        },
        line: {
          "line-color": "#0b1e3a",
          "line-width": 1.05,
          "line-opacity": 0.6,
        },
      },
      legend: [{ label: "No value", color: "#d9d9d9" }],
    },
    "oil-fields": {
      layer: "oil-fields",
      version: VERSION,
      minzoom: 0,
      maxzoom: 14,
      geometry: "polygon" as const,
      source_layer: "oil-fields",
      measure: null,
      attribution: "Synthetic oil attribution",
      style: {
        fill: { "fill-color": "#8a3b00", "fill-opacity": 0.28 },
        line: {
          "line-color": "#8a3b00",
          "line-width": 1.6,
          "line-opacity": 0.95,
        },
      },
      legend: [{ label: "Oil and gas fields", color: "#8a3b00" }],
    },
    platforms: {
      layer: "platforms",
      version: VERSION,
      minzoom: 0,
      maxzoom: 14,
      geometry: "point" as const,
      source_layer: "platforms",
      measure: null,
      attribution: "Synthetic platforms attribution",
      style: { circle: { "circle-color": "#8a3b00", "circle-radius": 4.5 } },
      legend: [{ label: "Platforms", color: "#8a3b00" }],
    },
    pipelines: {
      layer: "pipelines",
      version: VERSION,
      minzoom: 0,
      maxzoom: 14,
      geometry: "line" as const,
      source_layer: "pipelines",
      measure: null,
      attribution: "Synthetic pipelines attribution",
      style: {
        line: {
          "line-color": "#5c4a32",
          "line-width": 1.4,
          "line-opacity": 0.9,
        },
      },
      legend: [{ label: "Pipelines", color: "#5c4a32" }],
    },
  };
}

function scotlandExtentEntry() {
  return {
    layer: "scotland-extent",
    version: VERSION,
    minzoom: 0,
    maxzoom: 12,
    geometry: "polygon" as const,
    title: "Scotland land and sea area (illustrative)",
    source_layer: "scotland-extent",
    measure: null,
    attribution: SCOTLAND_EXTENT_CREDIT,
    style: {
      line: {
        "line-color": "#1f4e79",
        "line-width": 1.5,
        "line-opacity": 0.95,
      },
    },
    legend: [
      {
        label: "Scotland land and sea area (illustrative)",
        color: "#1f4e79",
      },
    ],
  };
}

function syntheticManifest(includeExtent: boolean) {
  const tilesets = {
    ...arch2bTilesets(),
    ...(includeExtent ? { "scotland-extent": scotlandExtentEntry() } : {}),
  };
  return { schema: 1, tilesets };
}

async function routeSeaExtentTiles(page: Page, includeExtent: boolean) {
  await routeManifestOverride(page, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(syntheticManifest(includeExtent)),
    });
  });

  await page.route("**/backend/v1/tiles/**/values/pop_density.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layer: "dz2022",
        version: VERSION,
        measure: "pop_density",
        values: { S01013482: 225.1 },
      }),
    });
  });

  await page.route("**/backend/v1/tiles/**/*.mvt", async (route) => {
    const url = route.request().url();
    let layer = "dz2022";
    if (url.includes("/scotland-extent/")) layer = "scotland-extent";
    else if (url.includes("/oil-fields/")) layer = "oil-fields";
    else if (url.includes("/platforms/")) layer = "platforms";
    else if (url.includes("/pipelines/")) layer = "pipelines";
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: MVT[layer],
    });
  });

  // Quiet context/open fetches when SE-E2 toggles every Layers switch.
  const emptyFc = JSON.stringify({ type: "FeatureCollection", features: [] });
  await page.route("**/backend/layers/context/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyFc,
    });
  });
  await page.route("**/backend/layers/open/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: emptyFc,
    });
  });
}

async function jump(page: Page, center: [number, number], zoom: number) {
  await page.evaluate(
    ({ c, z }) => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: c, zoom: z });
    },
    { c: center, z: zoom },
  );
}

async function outlineLayerState(page: Page) {
  return page.evaluate(() => {
    const map = (
      window as unknown as {
        __map?: {
          getLayer: (id: string) => unknown;
          getLayoutProperty: (id: string, prop: string) => unknown;
          getStyle: () => {
            layers?: { id?: string; type?: string }[];
          };
        };
      }
    ).__map;
    if (!map) return null;
    const layers = map.getStyle()?.layers ?? [];
    const ids = layers
      .map((l) => l.id)
      .filter((id): id is string => typeof id === "string");
    const outlineId = "tile-scotland-extent-line";
    const outlineIdx = ids.indexOf(outlineId);
    const firstSymbolIdx = layers.findIndex((l) => l.type === "symbol");
    const otherTileIdx = ids
      .map((id, i) => ({ id, i }))
      .filter(({ id }) => id.startsWith("tile-") && id !== outlineId)
      .map(({ i }) => i);
    const visibility =
      map.getLayer(outlineId) != null
        ? map.getLayoutProperty(outlineId, "visibility")
        : null;
    const extentLayerCount = ids.filter((id) =>
      id.startsWith("tile-scotland-extent-"),
    ).length;
    return {
      exists: map.getLayer(outlineId) != null,
      visibility,
      outlineIdx,
      firstSymbolIdx,
      otherTileIdx,
      extentLayerCount,
      ids,
    };
  });
}

// --- SE-U1 / SE-U2 (pure, no browser) ---

test("SE-U1 scotland-extent first in tile order, not in CONTEXT_LAYERS", () => {
  expect(TILE_LAYER_IDS_ORDERED[0]).toBe("scotland-extent");
  expect(CONTEXT_LAYERS.some((l) => l.id === "scotland-extent")).toBe(false);
});

test("SE-U2 short name and attribution piece order", () => {
  expect(
    shortLayerSourceName({
      id: "scotland-extent",
      text: SCOTLAND_EXTENT_CREDIT,
    }),
  ).toBe(SHORT_OUTLINE);
  expect(
    buildMapAttributionPieces(["scotland-extent"]).map((p) => p.id),
  ).toEqual(["basemap", "scotland-extent"]);
});

// --- SE-E1–E4 ---

test.describe("SEA-EXTENT-2 e2e", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("SE-E1 outline visible and below other tile layers and symbols", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await routeSeaExtentTiles(page, true);
    await openMap(page, "/?z=5&c=-4.5,56.5");
    await waitForMap(page);
    await jump(page, [-4.5, 56.5], 5);
    await expect
      .poll(async () => {
        const s = await outlineLayerState(page);
        return s?.exists === true && s.visibility !== "none";
      }, { timeout: 30_000 })
      .toBe(true);
    const state = await outlineLayerState(page);
    expect(state).not.toBeNull();
    expect(state!.visibility).not.toBe("none");
    expect(state!.outlineIdx).toBeGreaterThanOrEqual(0);
    for (const idx of state!.otherTileIdx) {
      expect(
        state!.outlineIdx,
        "outline style index must be below every other tile-* layer",
      ).toBeLessThan(idx);
    }
    if (state!.firstSymbolIdx >= 0) {
      expect(
        state!.outlineIdx,
        "outline style index must be below the first symbol layer",
      ).toBeLessThan(state!.firstSymbolIdx);
    }
    assertConsoleClean(gate);
  });

  test("SE-E2 outline stays on when every Layers switch toggles; no drawer row", async ({
    page,
    gate,
  }) => {
    test.setTimeout(180_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await routeSeaExtentTiles(page, true);
    await openMap(page, "/?z=5&c=-4.5,56.5");
    await waitForMap(page);
    await jump(page, [-4.5, 56.5], 5);
    await expect
      .poll(async () => (await outlineLayerState(page))?.exists === true, {
        timeout: 30_000,
      })
      .toBe(true);

    await openLayers(page);
    for (const key of ["land", "places", "resources", "sea", "energy", "use"]) {
      await ensureLayersGroupOpen(page, key);
    }
    const panel = page.getByTestId("layers-panel");
    const panelText = ((await panel.innerText()) ?? "").toLowerCase();
    expect(panelText).not.toMatch(/scotland-extent|land and sea|outline/i);

    const toggles = panel.locator("[data-testid^='layer-toggle-']");
    const count = await toggles.count();
    expect(count).toBeGreaterThan(0);
    for (let i = 0; i < count; i++) {
      const t = toggles.nth(i);
      if ((await t.getAttribute("aria-checked")) === "true") {
        await t.click();
      }
    }
    await expect
      .poll(async () => {
        const s = await outlineLayerState(page);
        return s?.exists === true && s.visibility !== "none";
      }, { timeout: 15_000 })
      .toBe(true);
    for (let i = 0; i < count; i++) {
      const t = toggles.nth(i);
      if ((await t.getAttribute("aria-checked")) !== "true") {
        await t.click();
      }
    }
    await expect
      .poll(async () => {
        const s = await outlineLayerState(page);
        return s?.exists === true && s.visibility !== "none";
      }, { timeout: 15_000 })
      .toBe(true);
    assertConsoleClean(gate);
  });

  test("SE-E4 missing scotland-extent: no layers, no short name, silence", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await routeSeaExtentTiles(page, false);
    await openMap(page, "/?z=5&c=-4.5,56.5");
    await waitForMap(page);
    await jump(page, [-4.5, 56.5], 5);
    await expect
      .poll(async () => (await outlineLayerState(page))?.extentLayerCount ?? -1, {
        timeout: 20_000,
      })
      .toBe(0);
    // CARD-CLARITY-31OCT-1A: short names are sheet-only; outline must not appear.
    const bar = await page.getByTestId("map-credit-line").innerText();
    expect(bar).not.toContain("Scotland outline");
    const shortInSheet = await readCreditShortNames(page);
    expect(shortInSheet).not.toContain("Scotland outline");
    await expect(page.getByText(SHORT_OUTLINE)).toHaveCount(0);
    await expect(page.getByText("One layer did not load.")).toHaveCount(0);
    assertConsoleClean(gate);
  });
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1440, height: 900 },
] as const) {
  test.describe(`SEA-EXTENT-2 SE-E3 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("SE-E3 credit short name and sheet/line long text", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await routeSeaExtentTiles(page, true);
      await openMap(page, "/?z=5&c=-4.5,56.5");
      await waitForMap(page);
      await jump(page, [-4.5, 56.5], 5);
      await expect
        .poll(async () => (await outlineLayerState(page))?.exists === true, {
          timeout: 30_000,
        })
        .toBe(true);
      const barText = await page.getByTestId("map-credit-line").innerText();
      expect(barText).not.toContain(SHORT_OUTLINE);
      expect(await readCreditShortNames(page)).toContain(SHORT_OUTLINE);

      if (viewport.width <= 900) {
        const visible = await page.getByTestId("map-credit-line").innerText();
        expect(visible).not.toContain("UK Hydrographic Office");
        expect(visible).not.toContain(SCOTLAND_EXTENT_CREDIT);
        expect(visible).not.toContain(SHORT_OUTLINE);
        await page.getByTestId("map-credit-info").click();
        const sheet = page.getByTestId("map-credit-sheet");
        await expect(sheet).toBeVisible();
        const sheetText = ((await sheet.textContent()) ?? "")
          .replace(/\s+/g, " ")
          .replace(/^[×x]\s*/i, "")
          .trim();
        expect(sheetText).toContain(SCOTLAND_EXTENT_CREDIT);
        await page.getByTestId("map-credit-sheet-close").click();
      } else {
        const attr = page.getByTestId("map-attribution-line");
        await expect(attr).toContainText(SCOTLAND_EXTENT_CREDIT);
      }
      assertConsoleClean(gate);
    });
  });
}
