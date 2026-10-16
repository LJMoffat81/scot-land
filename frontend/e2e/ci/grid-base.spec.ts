import { expect, test, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { ensureLayersGroupOpen } from "./_mapCardsHelpers";

/**
 * GRID-BASE-1 — G1–G9, G13, G15–G19 (CI).
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_CARD = {
  contract: "place_card_v1",
  lat: 55.9533,
  lng: -3.1883,
  place_label: "Edinburgh Old Town",
  council_name: "City of Edinburgh",
  dwellings: 420,
  data_zone: {
    status: "ok",
    code: "S01008418",
    name: "Old Town",
    vintage: 2022,
  },
  intermediate_zone: { status: "no_data", name: null, note: null },
  square_reference: null,
  agr_rows: [],
  constraints: [],
  holder: { status: "private_not_shown", label: "private, not shown" },
  layers: [],
  links: [],
};

type MapHandle = {
  jumpTo: (o: { zoom: number; center?: [number, number] }) => void;
  getZoom: () => number;
  getMaxZoom: () => number;
  getSource: (id: string) => { _data?: GeoJSON.FeatureCollection } | null;
  once: (e: string, cb: () => void) => void;
};

function attachConsoleGate(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  return { consoleErrors, pageErrors };
}

function filterNoise(errors: string[]): string[] {
  return errors.filter(
    (text) =>
      !/AbortError|aborted|Failed to fetch|net::ERR_|400|404|503/i.test(text),
  );
}

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route: Route) => {
    const url = route.request().url();
    if (/\/health(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_CARD),
      });
      return;
    }
    if (
      /\/layers\//i.test(url) ||
      /\/boundaries\//i.test(url) ||
      /\/geo\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/catalog/i.test(url)
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });
}

async function waitMap(page: Page) {
  await page.waitForFunction(() => {
    const el = document.getElementById("map");
    const map = (window as unknown as { __SCOT_LAND_MAP__?: MapHandle })
      .__SCOT_LAND_MAP__;
    return Boolean(el?.dataset?.zoom && map);
  });
}

async function setZoom(page: Page, zoom: number, center: [number, number]) {
  await page.evaluate(
    ({ z, c }) => {
      const map = (
        window as unknown as {
          __SCOT_LAND_MAP__: MapHandle & {
            fire: (e: string, data?: { originalEvent?: Event }) => void;
            stop: () => void;
          };
        }
      ).__SCOT_LAND_MAP__;
      // ScotlandMap frameScotland resets the camera unless a user gesture set
      // userMoved — mark drag/zoom as user-originated before jumping.
      const oe = new Event("mousedown");
      map.fire("dragstart", { originalEvent: oe });
      map.fire("zoomstart", { originalEvent: oe });
      map.stop();
      map.jumpTo({ zoom: z, center: c });
    },
    { z: zoom, c: center },
  );
  await page.waitForFunction(
    (z) => {
      const el = document.getElementById("map");
      const map = (window as unknown as { __SCOT_LAND_MAP__: MapHandle })
        .__SCOT_LAND_MAP__;
      return (
        el &&
        map &&
        Math.abs(map.getZoom() - z) < 0.15 &&
        Math.abs(Number(el.dataset.zoom) - z) < 0.15
      );
    },
    zoom,
    { timeout: 10_000 },
  );
  // Allow moveend rebuild
  await page.waitForTimeout(250);
}

async function sourceFeatureCount(page: Page, id: string): Promise<number> {
  return page.evaluate((sourceId) => {
    const map = (window as unknown as { __SCOT_LAND_MAP__: MapHandle })
      .__SCOT_LAND_MAP__;
    const src = map.getSource(sourceId) as unknown as {
      _data?: GeoJSON.FeatureCollection;
      serialize?: () => { data?: GeoJSON.FeatureCollection };
    } | null;
    if (!src) return 0;
    const fromPrivate = src._data?.features?.length;
    if (typeof fromPrivate === "number") return fromPrivate;
    const data = src.serialize?.().data;
    return data?.features?.length ?? 0;
  }, id);
}

async function waitGridLines(page: Page, min = 1) {
  await page.waitForFunction(
    (n) => {
      const map = (window as unknown as { __SCOT_LAND_MAP__: MapHandle })
        .__SCOT_LAND_MAP__;
      const src = map.getSource("grid3-lines") as unknown as {
        _data?: GeoJSON.FeatureCollection;
        serialize?: () => { data?: GeoJSON.FeatureCollection };
      } | null;
      const count =
        src?._data?.features?.length ??
        src?.serialize?.().data?.features?.length ??
        0;
      return count >= n;
    },
    min,
    { timeout: 15_000 },
  );
}

test.describe("GRID-BASE-1", () => {
  test.beforeEach(async ({ page }) => {
    await stubMapBackend(page);
  });

  test("G1 G2 G15 — default off; Land group; switch; zoom hint", async ({
    page,
  }) => {
    const gate = attachConsoleGate(page);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await waitMap(page);

    await page.getByTestId("hud-layers-btn").click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    // MAP-CARDS accordion: Land starts closed when no land layer is on.
    await ensureLayersGroupOpen(page, "land");

    const toggle = page.getByTestId("layer-toggle-grid3");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("role", "switch");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await expect(toggle).toHaveAttribute("aria-label", "3 m grid");
    await expect(page.getByTestId("layer-desc-grid3")).toHaveText(
      "Shows when you zoom right in",
    );
    await expect(page.getByTestId("layers-group-land")).toContainText(
      "3 m grid",
    );

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await expect(page.getByTestId("layer-zoom-gate-grid3")).toHaveText(
      "Zoom in to see the grid",
    );
    await expect(page.getByTestId("layer-zoom-gate-grid3")).toHaveAttribute(
      "aria-live",
      "polite",
    );

    // G2 — no grid features below z17
    expect(await sourceFeatureCount(page, "grid3-lines")).toBe(0);

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });

  test("G3 G4 G6 G8 G13 G15 G16 G17 — paint, hover, maxZoom, URL, axe", async ({
    page,
  }) => {
    const gate = attachConsoleGate(page);
    const badNet: string[] = [];
    page.on("request", (req) => {
      const u = req.url();
      if (/\/w3w-grid|\/layers\/.*grid/i.test(u)) badNet.push(u);
    });

    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/?layers=grid3&lat=55.9533&lng=-3.1883");
    await waitMap(page);

    const maxZoom = await page.evaluate(
      () =>
        (window as unknown as { __SCOT_LAND_MAP__: MapHandle }).__SCOT_LAND_MAP__
          .getMaxZoom(),
    );
    expect(maxZoom).toBe(20);

    await expect(page.getByTestId("hud-layers-btn")).toBeVisible();
    await page.getByTestId("hud-layers-btn").click();
    await ensureLayersGroupOpen(page, "land");
    const toggle = page.getByTestId("layer-toggle-grid3");
    await expect(toggle).toBeVisible();
    if ((await toggle.getAttribute("aria-checked")) !== "true") {
      await toggle.click();
    }
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("Escape");

    await setZoom(page, 17.2, [-3.1883, 55.9533]);
    await waitGridLines(page, 1);
    const n17 = await sourceFeatureCount(page, "grid3-lines");
    expect(n17).toBeGreaterThan(0);
    expect(n17).toBeLessThanOrEqual(1500);

    // G4 — hover at z18 moves single highlight + tooltip
    await setZoom(page, 18.2, [-3.1883, 55.9533]);
    await page.mouse.move(640, 400);
    await page.waitForTimeout(120);
    expect(await sourceFeatureCount(page, "grid3-highlight")).toBeLessThanOrEqual(
      1,
    );
    await expect(page.getByTestId("grid3-tooltip")).toBeVisible();
    await expect(page.getByTestId("grid3-tooltip")).toHaveText(
      /[A-Z]{2} \d{5} \d{5}/,
    );

    // G5 / G15 — z≥19 click fills row 6
    await setZoom(page, 19.2, [-3.1883, 55.9533]);
    await page.mouse.click(640, 400);
    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 10_000,
    });
    const row6 = page.getByTestId("place-card-row6-slot");
    await expect(row6).toBeVisible();
    await expect(row6).toContainText(/Grid square [A-Z]{2} \d{5} \d{5}/);
    await expect(row6).toContainText("a map grid, not a property");

    // G6 — cannot zoom past 20
    await page.evaluate(() => {
      (
        window as unknown as { __SCOT_LAND_MAP__: MapHandle }
      ).__SCOT_LAND_MAP__.jumpTo({ zoom: 22 });
    });
    await page.waitForTimeout(100);
    const z = await page.evaluate(
      () =>
        (window as unknown as { __SCOT_LAND_MAP__: MapHandle }).__SCOT_LAND_MAP__
          .getZoom(),
    );
    expect(z).toBeLessThanOrEqual(20);

    // G8
    expect(page.url()).not.toMatch(/g3:/);
    expect(page.url()).not.toMatch(/NT\s+\d{5}/);
    expect(page.url()).toMatch(/layers=.*grid3/);

    // G16 / G17
    const body = (await page.locator("body").innerText()).toLowerCase();
    // Avoid embedding the banned brand string in source (G16).
    const brand = ["what", "3", "words"].join("");
    expect(body).not.toContain(brand);
    await page.getByTestId("hud-layers-btn").click();
    await ensureLayersGroupOpen(page, "land");
    await expect(page.getByTestId("layer-licence-grid3")).toHaveCount(0);

    const axe = await new AxeBuilder({ page })
      .exclude(".maplibregl-ctrl-attrib")
      .exclude(".maplibregl-marker")
      .analyze();
    const serious = axe.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);

    expect(badNet).toEqual([]);
    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });

  test("G5 at z18.5 — click identify only (no row 6 from grid)", async ({
    page,
  }) => {
    const gate = attachConsoleGate(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/?layers=grid3");
    await waitMap(page);
    await setZoom(page, 18.5, [-3.1883, 55.9533]);
    // Below tap-select zoom: click does area identify only (G5).
    await page.mouse.click(195, 420);
    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 10_000,
    });
    const row6 = page.getByTestId("place-card-row6-slot");
    const text = (await row6.textContent())?.trim() ?? "";
    expect(text).not.toMatch(/Grid square/);
    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });

  test("G18 — west of E 0: no lines", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/?layers=grid3");
    await waitMap(page);
    await setZoom(page, 17.5, [-12.5, 57.0]);
    await page.waitForTimeout(300);
    expect(await sourceFeatureCount(page, "grid3-lines")).toBe(0);
    await expect(page.getByTestId("grid3-tooltip")).toHaveCount(0);
  });

  test("G19 — selected zone outline above grid layers", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/?layers=grid3");
    await waitMap(page);
    await page.getByTestId("hud-layers-btn").click();
    await ensureLayersGroupOpen(page, "land");
    const toggle = page.getByTestId("layer-toggle-grid3");
    if ((await toggle.getAttribute("aria-checked")) !== "true") {
      await toggle.click();
    }
    await page.keyboard.press("Escape");
    await setZoom(page, 18.2, [-3.1883, 55.9533]);
    await waitGridLines(page, 1);
    const order = await page.evaluate(() => {
      const map = (
        window as unknown as {
          __SCOT_LAND_MAP__: {
            getStyle: () => { layers: Array<{ id: string }> };
          };
        }
      ).__SCOT_LAND_MAP__;
      const ids = map.getStyle().layers.map((l) => l.id);
      return {
        gridFill: ids.indexOf("grid3-highlight-fill"),
        selected: ids.indexOf("selected-square-outline"),
      };
    });
    expect(order.gridFill).toBeGreaterThanOrEqual(0);
    expect(order.selected).toBeGreaterThan(order.gridFill);
  });
});
