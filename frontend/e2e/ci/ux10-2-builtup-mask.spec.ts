import { expect, test, type Page } from "@playwright/test";

/**
 * UX10-2 built-up mask — 390 and 1280; NRS+OS attribution visible; no £;
 * no parcel polygons; faint DZ outlines stay available; console/pageerror gate.
 */

const ATTRIBUTION = "NRS Settlements 2022 (OGL v3), contains OS data";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const MASK_FC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { code: "S01014567", layer: "dz2022_masked" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.26, 55.858],
            [-4.25, 55.858],
            [-4.25, 55.865],
            [-4.26, 55.865],
            [-4.26, 55.858],
          ],
        ],
      },
    },
  ],
  meta: {
    ok: true,
    attribution: ATTRIBUTION,
    licence: "OGL-3.0",
  },
};

const CATALOG = {
  version: 2,
  layers: [
    {
      id: "data_zones",
      group: "spatial",
      status: "live",
      label: "Data Zone boundaries",
      licence: "OGL-3.0",
      attribution:
        "Scottish Government Data Zone boundaries 2022 (OGL). Outlines only — not a rent.",
    },
    {
      id: "builtup_mask",
      group: "spatial",
      status: "live",
      label: "Built-up display mask",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      attribution: ATTRIBUTION,
      endpoint: "/layers/open/dz2022-masked",
      tile_endpoint: "/layers/open/dz2022-masked/tiles/{z}/{x}/{y}",
    },
  ],
};

type ConsoleGate = {
  consoleErrors: string[];
  pageErrors: string[];
};

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });
  return { consoleErrors, pageErrors };
}

function filterNoise(errors: string[]): string[] {
  return errors.filter(
    (text) =>
      !/AbortError|aborted|Failed to fetch|net::ERR_|400|404|503/i.test(text),
  );
}

async function stubMapBackend(page: Page) {
  // Single handler so Playwright LIFO cannot let a catch-all steal
  // /layers/catalog or dz2022-masked (credits would never mount).
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CATALOG),
      });
      return;
    }
    // Attribution under test does not need a live place card. A 200 place
    // payload lets ?lat=&lng= boot (and accidental map hits) keep a sheet
    // open that covers Show legend at 390 and keeps legendCompact so
    // map-licence-credits never mounts.
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "e2e stub: no place card" }),
      });
      return;
    }
    if (/\/place(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
      return;
    }
    if (/\/layers\/open\/dz2022-masked/i.test(url)) {
      if (/\/tiles\//i.test(url)) {
        await route.fulfill({
          status: 200,
          contentType: "application/vnd.mapbox-vector-tile",
          body: Buffer.alloc(0),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(MASK_FC),
      });
      return;
    }
    if (/\/layers\/open\/builtup-mask/i.test(url)) {
      if (/\/tiles\//i.test(url)) {
        await route.fulfill({
          status: 200,
          contentType: "application/vnd.mapbox-vector-tile",
          body: Buffer.alloc(0),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
      return;
    }
    if (/\/layers\/context\/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "e2e stub: no data zone" }),
      });
      return;
    }
    if (/\/platform\/gbp-live/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: false,
          banner: null,
          rent_rate_wording: null,
        }),
      });
      return;
    }
    if (/\/layers\//i.test(url)) {
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
      body: JSON.stringify({}),
    });
  });
  await page.route("**/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(CATALOG),
    });
  });
}

async function openTools(page: Page) {
  const layersBtn = page.getByTestId("hud-layers-btn");
  await expect(layersBtn).toBeVisible({ timeout: 30_000 });
  if ((await layersBtn.getAttribute("aria-pressed")) !== "true") {
    await layersBtn.click();
  }
  await expect(page.getByTestId("layers-panel")).toBeVisible({ timeout: 15_000 });
}

async function closeTools(page: Page) {
  const panel = page.getByTestId("layers-panel");
  if (!(await panel.isVisible().catch(() => false))) return;
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden({ timeout: 10_000 });
}

async function closePlaceCard(page: Page) {
  // Click × until the card is gone. Escape alone can leave a loading stub up;
  // a single click can race an in-flight ?lat=&lng= inspect that remounts.
  // force is only on × (sheet covers the hit target at 390) — not on asserts.
  await expect(async () => {
    const card = page.getByTestId("place-card");
    if ((await card.count()) === 0) return;
    const close = page.getByRole("button", { name: "Close place card" });
    if ((await close.count()) > 0) {
      await close.click({ force: true });
    } else {
      await page.keyboard.press("Escape");
    }
    await expect(page.getByTestId("place-card")).toHaveCount(0, {
      timeout: 3_000,
    });
  }).toPass({ timeout: 20_000 });
}

/**
 * Narrow layout hides licence credits until the legend fold is open.
 * SW-047: MapLicenceCredits is unmounted while a place card keeps
 * legendCompact. Close overlays first — place / layers intercept Show legend
 * at 390. URL ?lat=&lng= can reopen the place card after dismiss — retry
 * dismiss + open. Do not click the fold when credits are already visible
 * (place-close restores legendOpen; another click would toggle shut).
 */
async function ensureLegendOpen(page: Page) {
  await closeTools(page);
  // Boot inspect may still be mounting the place card — wait briefly then dismiss.
  await page
    .getByTestId("place-card")
    .waitFor({ state: "visible", timeout: 5_000 })
    .catch(() => {});
  const credits = page.getByTestId("map-licence-credits");
  const show = page.locator("button.hud-scotland-fold");
  const panel = page.getByTestId("map-legend-panel");
  for (let attempt = 0; attempt < 5; attempt++) {
    await closePlaceCard(page);
    await expect(panel).toHaveAttribute("data-legend-compact", "false", {
      timeout: 10_000,
    });
    if (await credits.isVisible().catch(() => false)) return;
    const foldVisible = await show.isVisible().catch(() => false);
    if (!foldVisible) {
      // Desktop: legend body shows without the fold control.
      await expect(credits).toBeVisible({ timeout: 15_000 });
      return;
    }
    if (await page.getByTestId("place-card").isVisible().catch(() => false)) {
      continue;
    }
    // Only click Show legend when the fold is closed — place-close may have
    // already restored legendOpen; clicking again would toggle the body shut.
    const needsOpen = await panel.evaluate(
      (el) => !el.classList.contains("legend-open"),
    );
    try {
      if (needsOpen) {
        await show.click({ timeout: 3_000, force: true });
      }
      await expect(credits).toBeVisible({ timeout: 15_000 });
      return;
    } catch {
      // Place card likely reopened over the fold; dismiss and retry.
    }
  }
  await closePlaceCard(page);
  await expect(page.getByTestId("place-card")).toHaveCount(0);
  await expect(panel).toHaveAttribute("data-legend-compact", "false", {
    timeout: 10_000,
  });
  if (await credits.isVisible().catch(() => false)) return;
  const needsOpen = await panel.evaluate(
    (el) => !el.classList.contains("legend-open"),
  );
  if (needsOpen && (await show.isVisible().catch(() => false))) {
    await show.click({ force: true });
  }
  await expect(credits).toBeVisible({ timeout: 15_000 });
  await credits.scrollIntoViewIfNeeded();
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`UX10-2 built-up mask ${viewport.width}`, () => {
    test.use({ viewport });

    test("attribution visible; no £; parcels stay off", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      // lat/lng fly zooms past DATA_ZONE_MIN_ZOOM (10) so dz2022-masked can
      // paint and MapLibre surfaces the source attribution (NRS/OS). Place card
      // is dismissed in ensureLegendOpen before Show legend.
      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });

      await openTools(page);
      const maskToggle = page.getByTestId("layer-toggle-builtup_mask");
      await expect(maskToggle).toBeVisible({ timeout: 30_000 });
      if ((await maskToggle.getAttribute("aria-pressed")) !== "true") {
        await maskToggle.click();
      }
      await expect(maskToggle).toHaveAttribute("aria-pressed", "true");

      // Faint full DZ outlines remain available as a toggle (click target).
      await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();

      // Parcels stay off (PARCELS-OFF).
      await expect(page.getByTestId("layer-toggle-boundaries")).toHaveCount(0);
      const parcelTile = await page.request.get("/api/parcels/tiles/14/8045/5230");
      expect(parcelTile.status()).toBe(404);

      await ensureLegendOpen(page);
      const credits = page.getByTestId("map-licence-credits");
      await expect(credits).toBeVisible({ timeout: 45_000 });
      const maskCredit = page.getByTestId("map-credit-builtup_mask");
      await maskCredit.scrollIntoViewIfNeeded();
      await expect(maskCredit).toBeVisible({
        timeout: 30_000,
      });
      await expect(credits).toContainText("NRS Settlements 2022");
      await expect(credits).toContainText("OS data");
      await expect(credits).toContainText(ATTRIBUTION);

      const bodyText = await page.locator("body").innerText();
      expect(bodyText).not.toMatch(/£\d/);
      expect(bodyText.toLowerCase()).not.toContain("natural capital");
      expect(bodyText.toLowerCase()).not.toMatch(/\bledger\b/);

      // Source attribution also lands on MapLibre's attribution control.
      const attrib = page.locator(".maplibregl-ctrl-attrib");
      await expect(attrib).toContainText(/NRS Settlements 2022|OS data/i, {
        timeout: 45_000,
      });

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}
