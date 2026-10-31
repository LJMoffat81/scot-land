/**
 * FRONTEND-BATCH-2 r6 — R1–R5 credit-line reconciliation.
 * Viewports 1280×800 and 390×844. Console errors fail the test.
 */
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  rmSync,
  readFileSync,
} from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { attachConsoleGate, assertConsoleClean, CI_TINY_PNG, DUMMY_ESRI_KEY, EMPTY_GLYPH_PBF, injectEsriBasemapKey, openLayers, openMap, openPlaceViaCoords, readCreditShortNames, registerOpenFreeMapFontStub, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";
import {
  BUILTUP_CREDIT_TEXT,
  buildMapAttributionPieces,
  shortLayerSourceName,
  VDL_ZONE_TOTALS_ATTRIBUTION,
} from "../../lib/mapAttributionLine";
import {
  LAYERS_ADD2_CREDITS,
  layersAdd2Credit,
} from "../../lib/layersAdd2Credits";
import { scanLibertyHits } from "./_libertyScan";

registerOpenFreeMapFontStub();

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

const STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

const NRS_PIECE = LAYERS_ADD2_CREDITS.nrs_dz_pop_hh.attribution;
const NRS_SHORT = shortLayerSourceName({
  id: "nrs_dz_pop_hh",
  text: NRS_PIECE,
})!;
const VDL_SHORT = shortLayerSourceName({
  id: "vdl",
  text: "x",
})!;

const OSM_CREDIT = "© OpenFreeMap © OpenStreetMap";
const LONG_VDL_MARKER = "Zones with one or two sites show no area.";

type Box = { x: number; y: number; width: number; height: number };

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function boxOf(locator: ReturnType<Page["locator"]>): Promise<Box> {
  const box = await locator.boundingBox();
  if (!box) throw new Error("missing box");
  return box;
}

async function routeEsriFixture(page: Page) {
  const style = JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as {
    sprite: string;
    sources: Record<string, unknown>;
  };
  await page.route(`${STYLE_URL}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(style),
    });
  });
  await page.route(`${style.sprite}.json`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ image: "root.png", width: 1, height: 1 }),
    });
  });
  await page.route(`${style.sprite}.png`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/basemaps-api.arcgis.com/**/*.pbf**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: EMPTY_GLYPH_PBF,
    });
  });
  await page.route("**/ibasemaps-api.arcgis.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route(
    "**/basemaps-api.arcgis.com/**/VectorTileServer**",
    async (route) => {
      const url = route.request().url();
      if (/\.pbf/i.test(url)) {
        await route.fulfill({
          status: 200,
          contentType: "application/x-protobuf",
          body: EMPTY_GLYPH_PBF,
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tiles: [
            "https://basemaps-api.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/tile/{z}/{y}/{x}.pbf",
          ],
          minzoom: 0,
          maxzoom: 22,
        }),
      });
    },
  );
}

/**
 * Visible credit order (Aerial): Esri → OSM → Sources (N).
 * Short layer names live in the ⓘ sheet only (CARD-CLARITY-31OCT-1A).
 * Uses innerText so hidden long pieces do not participate. Each index check can fail.
 * "Sources" uses lastIndexOf so Esri {A}'s "Sources: Esri, …" does not false-match.
 */
async function assertAerialVdlCreditOrder(page: Page) {
  const credit = page.getByTestId("map-credit-line");
  await expect(credit).toBeVisible();
  const visible = ((await credit.innerText()) ?? "").replace(/\s+/g, " ").trim();
  const esri = visible.indexOf("Powered by Esri");
  const osm = visible.indexOf(OSM_CREDIT);
  const sources = visible.lastIndexOf("Sources");
  expect(esri, `missing Powered by Esri in ${JSON.stringify(visible)}`).toBeGreaterThanOrEqual(0);
  expect(osm, `missing OSM credit in ${JSON.stringify(visible)}`).toBeGreaterThanOrEqual(0);
  expect(sources, `missing Sources in ${JSON.stringify(visible)}`).toBeGreaterThanOrEqual(0);
  expect(osm, `OSM must follow Esri`).toBeGreaterThan(esri);
  expect(sources, `Sources must follow OSM`).toBeGreaterThan(osm);
  expect(visible, `short name must leave the bar`).not.toContain(VDL_SHORT);
  await expect(page.getByTestId("map-all-sources")).toHaveText(/Sources \(\d+\)/);
}

async function enableAerialWithVdl(page: Page) {
  await injectEsriBasemapKey(page, DUMMY_ESRI_KEY);
  await stubMapCardsBackend(page);
  await routeEsriFixture(page);
  await openMap(page, "/?layers=vdl&z=12&c=-4.25,55.86");
  await waitForMap(page);
  await expect(page.getByTestId("basemap-switcher")).toBeVisible({
    timeout: 15_000,
  });
  await page.getByTestId("basemap-switcher").click();
  await expect(page.getByTestId("basemap-switcher")).toHaveAttribute(
    "aria-pressed",
    "true",
    { timeout: 30_000 },
  );
  await expect
    .poll(async () => page.getByTestId("map-credit-line").innerText(), {
      timeout: 30_000,
    })
    .toContain("Powered by Esri");
}

for (const viewport of VIEWPORTS) {
  test.describe(`FRONTEND-BATCH-2 r6 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("R1 layer pieces on the map", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/?layers=data_zones,vdl&z=12&c=-4.25,55.86");
      await waitForMap(page);

      const expected = buildMapAttributionPieces([
        "data_zones",
        "builtup_mask",
        "vdl",
      ])
        .map((p) => p.text)
        .join(" · ");
      const line = page.getByTestId("map-attribution-line");
      await expect(line).toBeVisible();
      await expect(page.getByTestId("map-credit-line")).toBeVisible();
      await expect
        .poll(
          async () =>
            ((await line.textContent()) ?? "").replace(/\s+/g, " ").trim(),
          { timeout: 15_000 },
        )
        .toBe(expected);
      const text = ((await line.textContent()) ?? "").replace(/\s+/g, " ").trim();
      expect(text).toBe(expected);
      assertConsoleClean(gate);
    });

    test("R2 narrow visible credit", async ({ page }) => {
      test.setTimeout(180_000);
      test.skip(viewport.width > 900, "R2 is the 390 narrow rule");
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/?layers=vdl&z=12&c=-4.25,55.86");
      await waitForMap(page);

      const credit = page.getByTestId("map-credit-line");
      await expect(credit).toBeVisible();
      const inner = await credit.innerText();
      expect(inner).toContain("© OpenFreeMap");
      expect(inner).toContain("© OpenStreetMap");
      expect(inner).toContain("Sources");
      // Short layer source name is sheet-only (CARD-CLARITY-31OCT-1A).
      expect(inner).not.toContain(VDL_SHORT);
      expect(await readCreditShortNames(page)).toContain(VDL_SHORT);
      // Long licence text must not repeat on the visible narrow line.
      expect(inner).not.toContain(LONG_VDL_MARKER);
      expect(VDL_ZONE_TOTALS_ATTRIBUTION).toContain(LONG_VDL_MARKER);
      await expect(
        page.getByRole("button", { name: "Map credits" }),
      ).toBeVisible();
      await expect(page.getByTestId("map-credit-info")).toHaveAttribute(
        "aria-label",
        "Map credits",
      );

      await enableAerialWithVdl(page);
      await assertAerialVdlCreditOrder(page);
      const aerialInner = await page.getByTestId("map-credit-line").innerText();
      expect(aerialInner).not.toContain(LONG_VDL_MARKER);
      expect(aerialInner).not.toContain(VDL_SHORT);
      expect(await readCreditShortNames(page)).toContain(VDL_SHORT);
      assertConsoleClean(gate);
    });

    test("R2b Aerial+vdl credit order (Esri → OSM → Sources (N); short in sheet)", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await enableAerialWithVdl(page);
      await assertAerialVdlCreditOrder(page);
      // Short name is in the ⓘ sheet only (can fail if it returns to the bar).
      await expect(page.getByTestId("map-credit-short-names")).toHaveCount(0);
      expect(await readCreditShortNames(page)).toContain(VDL_SHORT);
      if (viewport.width <= 900) {
        const visible = await page.getByTestId("map-credit-line").innerText();
        expect(visible).not.toContain(LONG_VDL_MARKER);
        expect(visible).not.toContain(VDL_SHORT);
        await expect(
          page.getByRole("button", { name: "Map credits" }),
        ).toHaveAttribute("aria-label", "Map credits");
      }
      assertConsoleClean(gate);
    });

    test("R3 credit clears panel / layers", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);
      const narrow = viewport.width <= 900;

      const credit = page.getByTestId("map-credit-line");
      await expect(credit).toBeVisible();

      await openLayers(page);
      const layers = page.getByTestId("layers-panel");
      await expect(layers).toBeVisible();
      if (await credit.isVisible().catch(() => false)) {
        expect(
          boxesOverlap(await boxOf(credit), await boxOf(layers)),
          "map-credit-line vs layers-panel",
        ).toBe(false);
      }

      for (const detent of ["peek", "half", "full"] as const) {
        await page.evaluate((d) => {
          const slot = document.querySelector(
            '[data-testid="map-panel-slot"]',
          );
          if (!slot) return;
          slot.classList.remove(
            "map-panel-slot--peek",
            "map-panel-slot--half",
            "map-panel-slot--full",
          );
          slot.classList.add(`map-panel-slot--${d}`);
          document.querySelector(".app-shell")?.classList.add("tools-open");
        }, detent);
        if (detent === "full" && narrow) {
          await expect(credit).toBeHidden();
        } else if (await credit.isVisible().catch(() => false)) {
          const slot = page.getByTestId("map-panel-slot");
          if (await slot.isVisible().catch(() => false)) {
            expect(
              boxesOverlap(await boxOf(credit), await boxOf(slot)),
              `map-credit-line vs panel ${detent}`,
            ).toBe(false);
          }
        }
      }

      await page.getByTestId("map-panel-slot-close").click().catch(() => undefined);
      await openPlaceViaCoords(page);
      const placeSlot = page.getByTestId("map-panel-slot");
      await expect(placeSlot).toBeVisible();
      if (await credit.isVisible().catch(() => false)) {
        expect(
          boxesOverlap(await boxOf(credit), await boxOf(placeSlot)),
          "map-credit-line vs place panel",
        ).toBe(false);
      }
      assertConsoleClean(gate);
    });

    test("R4 NRS credit + short name", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      expect(layersAdd2Credit("nrs_dz_pop_hh")).toBe(NRS_PIECE);
      await openMap(page, "/?layers=nrs_dz_pop_hh");
      await waitForMap(page);

      const line = page.getByTestId("map-attribution-line");
      await expect(line).toBeVisible();
      await expect
        .poll(async () => ((await line.textContent()) ?? "").includes(NRS_PIECE), {
          timeout: 15_000,
        })
        .toBe(true);
      await expect(line).toContainText(NRS_PIECE);
      // MAP-VISION-1b: layers=nrs falls through to defaultOn data_zones credit.
      const expected = buildMapAttributionPieces([
        "data_zones",
        "nrs_dz_pop_hh",
      ])
        .map((p) => p.text)
        .join(" · ");
      const text = ((await line.textContent()) ?? "").replace(/\s+/g, " ").trim();
      expect(text).toBe(expected);

      const inner = await page.getByTestId("map-credit-line").innerText();
      expect(inner).toContain(NRS_SHORT);
      if (viewport.width <= 900) {
        expect(inner).not.toContain(
          "Contains National Records of Scotland data licensed",
        );
        await expect(
          page.getByRole("button", { name: "Map credits" }),
        ).toBeVisible();
        await expect(page.getByTestId("map-credit-info")).toHaveAttribute(
          "aria-label",
          "Map credits",
        );
      }
      assertConsoleClean(gate);
    });
  });
}

test("R5 MC11 scan self-test", async () => {
  const dir = mkdtempSync(join(tmpdir(), "fb2-r6-scan-"));
  try {
    const sub = join(dir, "lib");
    mkdirSync(sub);
    writeFileSync(join(sub, "probe.ts"), "const x = 'liberty';\n");
    const { hits, filesScanned } = scanLibertyHits(["lib"], dir);
    expect(filesScanned).toBeGreaterThanOrEqual(1);
    expect(hits).toHaveLength(1);
    expect(hits[0]).toMatch(/probe\.ts:1$/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("R6 builtup short name", () => {
  expect(
    shortLayerSourceName({
      id: "builtup_mask",
      text: BUILTUP_CREDIT_TEXT,
    }),
  ).toBe("Built-up areas: NRS");
  expect(
    buildMapAttributionPieces(["builtup_mask"]).map((p) => p.id),
  ).toEqual(["basemap", "builtup_mask"]);
});

const E1_VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 1440, height: 900 },
] as const;

for (const viewport of E1_VIEWPORTS) {
  test.describe(`SRC-B-SETTLEMENTS E1 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("builtup short name at zoom 12; long credit in sheet/line", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/?z=6&c=-4.25,55.86");
      await waitForMap(page);
      await expect
        .poll(
          async () => page.locator("#map").getAttribute("data-framed"),
          { timeout: 30_000 },
        )
        .toBe("1");

      const credit = page.getByTestId("map-credit-line");
      await expect(credit).toBeVisible();
      expect(await credit.innerText()).not.toContain("Built-up areas: NRS");

      await page.evaluate(async () => {
        const map = (
          window as unknown as {
            __map?: {
              jumpTo(opts: {
                center: [number, number];
                zoom: number;
              }): void;
              once(event: string, cb: () => void): void;
            };
          }
        ).__map;
        if (!map) throw new Error("window.__map missing");
        await new Promise<void>((resolve) => {
          map.once("idle", () => resolve());
          map.jumpTo({ center: [-4.25, 55.86], zoom: 12 });
        });
      });

      await expect
        .poll(async () => readCreditShortNames(page), { timeout: 15_000 })
        .toContain("Built-up areas: NRS");
      expect(await credit.innerText()).not.toContain("Built-up areas: NRS");

      if (viewport.width <= 900) {
        await expect(page.locator(".map-credit-long-pieces")).toBeHidden();
        const visible = await credit.innerText();
        expect(visible).not.toContain(BUILTUP_CREDIT_TEXT);
        await page.getByTestId("map-credit-info").click();
        await expect(page.getByTestId("map-credit-sheet")).toContainText(
          BUILTUP_CREDIT_TEXT,
        );
        await page.keyboard.press("Escape");
      } else {
        await expect(page.getByTestId("map-attribution-line")).toContainText(
          BUILTUP_CREDIT_TEXT,
        );
      }
      assertConsoleClean(gate);
    });
  });
}
