/**
 * FRONTEND-BATCH-4 — SW-086 + SW-085 + MAP-HINTS-OFF-1.
 * Viewports 1280×800 and 390×844. Console errors fail. Batch 1 stubs.
 */
import { test, expect } from "./_fixtures";
import { type Page, type Route } from "@playwright/test";
import {
  DEFAULT_VIEW_METRIC_ID,
  POP_DENSITY_LEGEND_SOURCE,
  metricById,
  rangeLegendTitle,
} from "../../lib/mapColourRamps";
import { rangeLegendFromStops } from "../../lib/mapLicenceCredits";
import { PLACE_CARD_NO_MATCH } from "../../lib/placeCard";
import {
  PLACE_CARD_ESTIMATE_LINE,
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_TEXT,
  SEARCH_HINT_SR,
} from "../../lib/siteNav";
import { TRY_AGAIN } from "../../lib/api";
import { assertConsoleClean, attachConsoleGate, boxesOverlap, ensureLayersGroupOpen, openLayers, openMap, openPlaceViaCoords, registerOpenFreeMapFontStub, stubMapCardsBackend, type ConsoleGate } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

const COUNCIL_FC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {
        name: "Glasgow City",
        population_density_per_km2: 3520,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.32, 55.82],
            [-4.18, 55.82],
            [-4.18, 55.9],
            [-4.32, 55.9],
            [-4.32, 55.82],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        name: "Highland",
        population_density_per_km2: 9,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-5.2, 57.0],
            [-4.6, 57.0],
            [-4.6, 57.5],
            [-5.2, 57.5],
            [-5.2, 57.0],
          ],
        ],
      },
    },
  ],
} as const;

const BOUNDARIES_FC = {
  type: "FeatureCollection",
  features: COUNCIL_FC.features.map((f) => ({
    type: "Feature" as const,
    properties: { name: f.properties.name },
    geometry: f.geometry,
  })),
};

const EXPECTED_BANDS = [
  "10–100",
  "100–500",
  "500–1,500",
  "1,500–3,000",
  "3,000 and above",
] as const;

const RENT_RATE_HOW_IT_WORKS =
  "We turn land value into a yearly rent of up to 4.5% of that value.";

type Box = { x: number; y: number; width: number; height: number };

type MapProbe = {
  once(event: string, cb: () => void): void;
  jumpTo(opts: { zoom: number; center?: [number, number] }): void;
  isStyleLoaded?: () => boolean;
};

async function stubCouncilsOk(page: Page) {
  await page.route("**/layers/councils**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(COUNCIL_FC),
    });
  });
  await page.route("**/boundaries/councils**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(BOUNDARIES_FC),
    });
  });
}

async function getMap(page: Page): Promise<void> {
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const map = (window as unknown as { __map?: MapProbe }).__map;
          return Boolean(map && map.isStyleLoaded?.());
        }),
      { timeout: 60_000 },
    )
    .toBe(true);
}

async function jumpToZoom(page: Page, zoom: number): Promise<void> {
  await page.evaluate(async (z) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    await new Promise<void>((resolve) => {
      map.once("idle", () => resolve());
      map.jumpTo({ zoom: z, center: [-4.2, 56.8] });
    });
  }, zoom);
}

async function openDensityMap(page: Page, gate: ConsoleGate) {
  await stubMapCardsBackend(page, { gbpLive: false });
  await stubCouncilsOk(page);
  await openMap(page, "/");
  await getMap(page);
  await jumpToZoom(page, 6);
  await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
  await expect(page.getByTestId("legend-strip")).toHaveCount(0);
  await openLayers(page);
  await ensureLayersGroupOpen(page, "places");
  await expect(page.getByTestId("map-layer-pop-density-key")).toBeVisible({
    timeout: 45_000,
  });
  assertConsoleClean(gate);
}

function boxOf(el: { boundingBox(): Promise<Box | null> }) {
  return el.boundingBox();
}

async function assertLegendBands(page: Page, root: ReturnType<Page["locator"]>) {
  const metric = metricById("pop_density")!;
  const fromStops = rangeLegendFromStops(metric.stops, {
    metricId: metric.id,
    unit: metric.unit,
  });
  const expectedFromStops = fromStops.ranges.map((row) =>
    row.to === "and above" ? `${row.from} and above` : `${row.from}–${row.to}`,
  );
  expect(expectedFromStops).toEqual([...EXPECTED_BANDS]);

  const texts = root.getByTestId("map-range-legend-text");
  await expect(texts).toHaveCount(EXPECTED_BANDS.length);
  for (let i = 0; i < EXPECTED_BANDS.length; i += 1) {
    await expect(texts.nth(i)).toHaveText(EXPECTED_BANDS[i]);
  }
  await expect(root.getByTestId("map-range-legend-no-data")).toHaveText(
    "No data",
  );
  const title = rangeLegendTitle(metricById(DEFAULT_VIEW_METRIC_ID)!);
  expect(title).not.toBe("");
  await expect(root.getByTestId("map-range-legend-title")).toHaveText(title);
}

function placeWithFigure() {
  return {
    contract: "place_card_v1",
    lat: 55.8609,
    lng: -4.2514,
    place_label: "Glasgow City Centre",
    council_name: "Glasgow City",
    dwellings: 410,
    sales_year_from: 2019,
    sales_year_to: 2023,
    confidence: "Medium",
    data_zone: {
      status: "ok",
      code: "S01014567",
      name: "City Centre South",
      vintage: 2022,
    },
    intermediate_zone: { status: "ok", name: "City Centre", code: "S02002645" },
    agr_rows: [
      {
        id: "surface",
        label: "Land",
        tag: "proxy",
        class: "proxy",
        status: "in_progress",
        applies: true,
        range: "not yet estimated",
        unit: null,
        confidence: null,
        method: null,
        gloss: "The yearly rental value of the land under homes, without the buildings.",
      },
    ],
    constraints: [],
    holder: { status: "private_not_shown", label: "private, not shown" },
    layers: [],
    links: [],
    gbp_live: {
      enabled: true,
      banner: "Early estimates; ranges are wide and will change.",
      rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
      unit: "per m²",
      unit_wording: "per square metre of land, per year",
    },
    surface_rent_display: {
      state: "ok",
      low: 0.06,
      central: 0.12,
      high: 0.18,
      estimate_label: "Partly estimated",
      rent_rate_wording:
        "Yearly rent: up to 4.5% of the land's value",
      unit: "per m²",
      unit_wording: "per square metre of land, per year",
      grain: "data_zone",
    },
  };
}

for (const viewport of VIEWPORTS) {
  test.describe(`FRONTEND-BATCH-4 ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport });

    test("T-K1 credit in Layers", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDensityMap(page, gate);
      const key = page.getByTestId("map-layer-pop-density-key");
      await expect(key).toBeVisible();
      const councils = page.getByTestId("map-layer-councils");
      await expect(councils).toBeVisible();
      const order = await page.evaluate(() => {
        const c = document.querySelector('[data-testid="map-layer-councils"]');
        const k = document.querySelector(
          '[data-testid="map-layer-pop-density-key"]',
        );
        if (!c || !k || !c.parentElement) return false;
        const kids = [...c.parentElement.children];
        return kids.indexOf(k) === kids.indexOf(c) + 1;
      });
      expect(order).toBe(true);
      const source = key.getByTestId("map-range-legend-source");
      await source.scrollIntoViewIfNeeded();
      await expect(source).toBeVisible();
      await expect(source).toHaveText(POP_DENSITY_LEGEND_SOURCE);
      await expect(source).toContainText(/National Records of Scotland/);
      await expect(source).toContainText(/Open Government Licence v3\.0/);
      await expect(
        page
          .getByTestId("layers-panel")
          .getByTestId("map-range-legend-source"),
      ).toHaveCount(1);
      const box = await source.boundingBox();
      expect(box).toBeTruthy();
      expect(box!.width).toBeGreaterThan(0);
      expect(box!.height).toBeGreaterThan(0);
      assertConsoleClean(gate);
    });

    test("T-K2 credit on the map key", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDensityMap(page, gate);
      await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
      await expect(page.getByTestId("legend-strip")).toHaveCount(0);
      const source = page
        .getByTestId("map-layer-pop-density-key")
        .getByTestId("map-range-legend-source");
      await expect(source).toBeVisible();
      await expect(source).toHaveText(POP_DENSITY_LEGEND_SOURCE);
      assertConsoleClean(gate);
    });

    test("T-K3 key visible, clear of the search bar", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDensityMap(page, gate);
      await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
      await expect(page.getByTestId("legend-strip")).toHaveCount(0);
      const key = page.getByTestId("map-layer-pop-density-key");
      await expect(key).toBeVisible();
      const keyBox = await boxOf(key);
      expect(keyBox).toBeTruthy();
      const search = page.locator(".hud-search");
      const dock = page.locator(".hud-search-dock");
      const attrib = page.getByTestId("map-attribution-line");
      await expect(attrib).toBeVisible();
      const searchBox = await boxOf(search);
      const dockBox = await boxOf(dock);
      const attribBox = await boxOf(attrib);
      expect(searchBox).toBeTruthy();
      expect(dockBox).toBeTruthy();
      expect(attribBox).toBeTruthy();
      expect(boxesOverlap(keyBox!, searchBox!)).toBe(false);
      expect(boxesOverlap(keyBox!, dockBox!)).toBe(false);
      expect(boxesOverlap(keyBox!, attribBox!)).toBe(false);
      const topEl = await page.evaluate(() => {
        const keyEl = document.querySelector(
          '[data-testid="map-layer-pop-density-key"]',
        ) as HTMLElement | null;
        if (!keyEl) return null;
        const r = keyEl.getBoundingClientRect();
        const el = document.elementFromPoint(
          r.left + r.width / 2,
          r.top + r.height / 2,
        );
        return el?.closest('[data-testid="map-layer-pop-density-key"]') != null;
      });
      expect(topEl).toBe(true);
      assertConsoleClean(gate);
    });

    test("T-K4 bands", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDensityMap(page, gate);
      await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
      await expect(page.getByTestId("legend-strip")).toHaveCount(0);
      await assertLegendBands(
        page,
        page.getByTestId("map-layer-pop-density-key"),
      );
      assertConsoleClean(gate);
    });

    test("T-K5 chip toggle", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDensityMap(page, gate);
      await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
      await expect(page.getByTestId("legend-strip")).toHaveCount(0);
      const key = page.getByTestId("map-layer-pop-density-key");
      await expect(key).toBeVisible();
      await expect(key.getByTestId("map-range-legend-bands")).toBeVisible();
      const keyBox = await boxOf(key);
      const searchBox = await boxOf(page.locator(".hud-search"));
      expect(keyBox && searchBox).toBeTruthy();
      expect(boxesOverlap(keyBox!, searchBox!)).toBe(false);
      assertConsoleClean(gate);
    });

    test("T-H1 search hint gone", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await page.locator("#place-query").focus();
      await expect(page.getByTestId("search-empty-hint")).toHaveCount(0);
      // Spec: no *visible* element with SEARCH_HINT_SR (sr-only #search-hint stays).
      const visibleHint = await page.evaluate((hint) => {
        const nodes = [...document.querySelectorAll("body *")].filter((el) => {
          const t = (el.textContent || "").trim();
          return t === hint;
        });
        return nodes.some((el) => {
          const r = el.getBoundingClientRect();
          const style = getComputedStyle(el);
          if (style.display === "none" || style.visibility === "hidden") {
            return false;
          }
          return r.width > 1 && r.height > 1;
        });
      }, SEARCH_HINT_SR);
      expect(visibleHint).toBe(false);
      await expect(page.locator("#place-query")).toHaveAttribute(
        "placeholder",
        "Search a postcode or place",
      );
      assertConsoleClean(gate);
    });

    test("T-H2 accessibility", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      const input = page.locator("#place-query");
      await expect(input).toHaveAttribute("aria-describedby", "search-hint");
      const hint = page.locator("#search-hint");
      await expect(hint).toHaveCount(1);
      await expect(hint).toHaveText(SEARCH_HINT_SR);
      const hidden = await hint.evaluate((el) => {
        const style = getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return {
          display: style.display,
          ariaHidden: el.getAttribute("aria-hidden"),
          w: r.width,
          h: r.height,
          clip: style.clip,
          overflow: style.overflow,
        };
      });
      expect(hidden.display).not.toBe("none");
      expect(hidden.ariaHidden).not.toBe("true");
      const clipped =
        (hidden.w <= 1 && hidden.h <= 1) ||
        hidden.clip.includes("rect(0") ||
        hidden.overflow === "hidden";
      expect(clipped).toBe(true);
      assertConsoleClean(gate);
    });

    test("T-H3 search still works", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      // Intentional place 404 on EH1 1AA Enter → TRY_AGAIN.
      // Prefer 404 over route.abort: suggest's isServiceFailure catch clears the
      // note on abort/5xx, which races Enter under load.
      gate.expectError({
        urlPath: "/backend/place",
        status: 404,
        count: 1,
      });
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);

      await page.unroute("**/backend/place**");
      await page.route("**/backend/place**", async (route) => {
        const url = new URL(route.request().url());
        const q = (url.searchParams.get("q") || "").trim();
        if (/edin/i.test(q)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              kind: "places",
              matches: [
                {
                  label: "Edinburgh",
                  lat: 55.9533,
                  lng: -3.1883,
                },
              ],
            }),
          });
          return;
        }
        if (/^eh1\s*1yz$/i.test(q)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              kind: "point",
              lat: 55.9508,
              lng: -3.1875,
              label: "EH1 1YZ",
            }),
          });
          return;
        }
        if (/zzz/i.test(q)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ kind: "places", matches: [] }),
          });
          return;
        }
        if (/^eh1\s*1aa$/i.test(q)) {
          // Empty body → apiFetch maps 404 to TRY_AGAIN visitor copy.
          await route.fulfill({
            status: 404,
            contentType: "application/json",
            body: "{}",
          });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ kind: "places", matches: [] }),
        });
      });
      await page.route("**/geocode/postcode**", async (route) => {
        await route.abort("failed");
      });
      await page.route("**/platform/place**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            contract: "place_card_v1",
            lat: 55.9508,
            lng: -3.1875,
            place_label: "Edinburgh, Old Town",
            council_name: "City of Edinburgh",
            data_zone: {
              status: "ok",
              code: "S01008677",
              name: "Old Town",
              vintage: 2022,
            },
            intermediate_zone: {
              status: "ok",
              name: "Old Town",
              code: "S02001622",
            },
            agr_rows: [
              {
                id: "surface",
                label: "Land",
                tag: "proxy",
                status: "in_progress",
                applies: true,
              },
            ],
            constraints: [],
            layers: [],
            links: [],
          }),
        });
      });

      await openMap(page, "/");

      await page.locator("#place-query").fill("Edin");
      await expect(
        page.locator("#place-suggestions").getByRole("option").first(),
      ).toBeVisible({ timeout: 15_000 });

      // Prefer Enter over Search click so blur does not clear suggestNote (180ms).
      await page.locator("#place-query").fill("EH1 1YZ");
      await page.locator("#place-query").press("Enter");
      await expect(page.getByTestId("place-card")).toBeVisible({
        timeout: 45_000,
      });
      await page.getByTestId("place-card-close").click();

      await page.locator("#place-query").fill("ZZZQQQ999");
      await page.locator("#place-query").press("Enter");
      await expect(page.getByTestId("search-no-match")).toHaveText(
        PLACE_CARD_NO_MATCH,
      );

      // Set query + submit in one evaluate so the 250ms suggest debounce never
      // fires (runSearch clears the timer). Avoids suggest/Enter 404 count races.
      const place404 = page.waitForResponse(
        (res) =>
          /\/backend\/place/i.test(res.url()) &&
          /q=EH1/i.test(res.url()) &&
          res.status() === 404,
      );
      await page.locator("#place-query").evaluate((el) => {
        const input = el as HTMLInputElement;
        const native = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          "value",
        )?.set;
        native?.call(input, "EH1 1AA");
        input.dispatchEvent(new Event("input", { bubbles: true }));
        const go = document.querySelector(".hud-search-go");
        if (go instanceof HTMLElement) go.click();
      });
      await place404;
      await expect(
        page.locator(".search-suggest-note", { hasText: TRY_AGAIN }),
      ).toBeVisible({ timeout: 20_000 });
      await expect(page.getByText(TRY_AGAIN, { exact: true }).first()).toBeVisible();
      assertConsoleClean(gate);
    });

    test("T-H4 prompt card gone", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await expect(page.getByTestId("map-rest-prompt")).toHaveCount(0);
      await expect(
        page.getByText("Search a place or pick a layer."),
      ).toHaveCount(0);
      await openPlaceViaCoords(page);
      await page.getByTestId("place-card-close").click();
      await expect(page.getByTestId("map-rest-prompt")).toHaveCount(0);
      await expect(
        page.getByText("Search a place or pick a layer."),
      ).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("T-H5 place cards stay", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await page.route("**/backend/place**", async (route) => {
        const url = new URL(route.request().url());
        const q = (url.searchParams.get("q") || "").trim();
        if (/^eh1\s*1yz$/i.test(q)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              kind: "point",
              lat: 55.9508,
              lng: -3.1875,
              label: "EH1 1YZ",
            }),
          });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ kind: "places", matches: [] }),
        });
      });
      await openMap(page, "/");
      await page.locator("#place-query").fill("EH1 1YZ");
      await page.locator(".hud-search-go").click();
      await expect(page.getByTestId("place-card")).toBeVisible({
        timeout: 45_000,
      });
      await page.getByTestId("place-card-close").click();
      await openPlaceViaCoords(page);
      await expect(page.getByTestId("place-card")).toBeVisible();
      assertConsoleClean(gate);
    });

    test("T-H6 banner gone from map", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await expect(page.getByTestId("research-banner")).toHaveCount(0);
      await expect(page.getByText(RESEARCH_BANNER_BODY)).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("T-H7 How we built this keeps full text (guard)", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      for (const path of ["/how-we-built-this", "/data", "/place"]) {
        await page.goto(path);
        const banner = page.getByTestId("research-banner");
        await expect(banner).toBeVisible({ timeout: 30_000 });
        // Narrow strip collapses; expand so the full RESEARCH_BANNER_TEXT is present.
        const toggle = page.getByTestId("research-banner-toggle");
        if (
          (await toggle.count()) > 0 &&
          (await banner.getAttribute("data-expanded")) === "0"
        ) {
          await toggle.click();
        }
        await expect(banner).toContainText(RESEARCH_BANNER_TEXT);
      }
      assertConsoleClean(gate);
    });

    // T-H8 covers the place-card figure surface only. PlaceHectareStack /
    // LedgerPanel still show placeholders (no live figure), so "every figure
    // surface" on the map reduces to this card until real figures land.
    test("T-H8 estimate line, flag ON", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const place = placeWithFigure();
      await stubMapCardsBackend(page, { gbpLive: true, place });
      await stubCouncilsOk(page);
      await openPlaceViaCoords(page);
      const card = page.getByTestId("place-card");
      const figure = card.getByTestId("place-card-figure");
      await expect(figure).toBeVisible();
      await expect(card.getByTestId("place-card-figure-range")).toBeVisible();
      const line = card.getByTestId("place-card-estimate-line");
      await expect(line).toHaveText(PLACE_CARD_ESTIMATE_LINE);
      await expect(line).toBeVisible();
      const sib = await page.evaluate(() => {
        const fig = document.querySelector(
          '[data-testid="place-card-figure"]',
        );
        const est = document.querySelector(
          '[data-testid="place-card-estimate-line"]',
        );
        if (!fig || !est) return { ok: false, gap: 999 };
        const next = fig.nextElementSibling;
        const fr = fig.getBoundingClientRect();
        const er = est.getBoundingClientRect();
        return {
          ok: next === est,
          gap: er.top - fr.bottom,
        };
      });
      expect(sib.ok).toBe(true);
      expect(sib.gap).toBeLessThanOrEqual(16);
      assertConsoleClean(gate);
    });

    test("T-H9 estimate line, flag OFF, no figure", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openPlaceViaCoords(page);
      const card = page.getByTestId("place-card");
      await expect(card.getByTestId("place-card-figure-range")).toHaveCount(0);
      await expect(card.getByTestId("place-card-estimate-line")).toHaveCount(0);
      await expect(card.getByTestId("place-card-figure-status")).toHaveText(
        "Not published yet",
      );
      assertConsoleClean(gate);
    });

    test("T-H10 invariant", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);

      await stubMapCardsBackend(page, {
        gbpLive: true,
        place: placeWithFigure(),
      });
      await stubCouncilsOk(page);
      await openPlaceViaCoords(page);
      let card = page.getByTestId("place-card");
      // Flag-ON branch: stub must yield a figure so the invariant is not vacuous.
      await expect(card.getByTestId("place-card-figure")).toBeVisible();
      await expect(card.getByTestId("place-card-figure-range")).toBeVisible();
      const figOn = await card.getByTestId("place-card-figure-range").count();
      const lineOn = await card.getByTestId("place-card-estimate-line").count();
      expect(figOn).toBeGreaterThan(0);
      expect(lineOn).toBeGreaterThanOrEqual(1);

      await page.getByTestId("place-card-close").click();
      await stubMapCardsBackend(page, { gbpLive: false });
      await openPlaceViaCoords(page);
      card = page.getByTestId("place-card");
      const figOff = await card.getByTestId("place-card-figure-range").count();
      const lineOff = await card
        .getByTestId("place-card-estimate-line")
        .count();
      if (figOff > 0) expect(lineOff).toBeGreaterThanOrEqual(1);
      if (figOff === 0) expect(lineOff).toBe(0);
      assertConsoleClean(gate);
    });
  });
}
