import { expect, test, type Page } from "@playwright/test";

/**
 * WORDING-BATCH-1 — frozen wording/layout batch (ideas 55/41/18/53/26/52/17/24,
 * SW-033, SW-047+56, idea 57). Asserts at 390 and 1280. Fail on console errors.
 * No £ / banned visitor words.
 */

const BANNED =
  /\b(natural capital|ledger|headline|shadow|yield|what3words)\b/i;

const MASK_COPY =
  "Shows where towns and villages are (for later map colour). Display only — not a rent.";

const PARTS_SUMMARY = "Natural resource rents and services of nature";

const LAND_VALUES_COMING_SOON =
  "Land values coming soon — our method is still being tested.";
const PRE_POUND =
  "We're not showing amounts yet while we check our method.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_STUB = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow",
  council_name: "Glasgow City",
  square_reference: "2068927,-157234",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
  dwellings: 120,
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "shadow",
      class: "shadow",
      status: "in_progress",
      applies: true,
      range: "not yet estimated",
    },
    {
      id: "resource",
      label: "Natural resource rents",
      tag: "shadow",
      class: "shadow",
      status: "coming_soon",
      applies: true,
      range: "not yet estimated",
    },
    {
      id: "nature",
      label: "Services of nature",
      tag: "shadow",
      class: "shadow",
      status: "coming_soon",
      applies: true,
      range: "not yet estimated",
    },
  ],
  constraints: [],
  layers: [],
  links: [],
};

const CATALOG_WITH_MASK = {
  version: 2,
  layers: [
    {
      id: "data_zones",
      group: "spatial",
      status: "live",
      label: "Data Zone boundaries",
      licence: "OGL-3.0",
    },
    {
      id: "builtup_mask",
      group: "spatial",
      status: "live",
      label: "Built-up display mask",
      licence: "OGL-3.0",
      attribution: "NRS Settlements 2022 (OGL v3), contains OS data",
      endpoint: "/layers/open/dz2022-masked",
    },
    {
      id: "vdl",
      group: "spatial",
      status: "live",
      label: "Vacant and derelict land",
      licence: "OGL-3.0",
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
    if (msg.type() === "error") consoleErrors.push(msg.text());
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

async function stubMapBackend(
  page: Page,
  opts: { maskStatus?: number; catalog?: unknown } = {},
) {
  const maskStatus = opts.maskStatus ?? 200;
  const catalog = opts.catalog ?? CATALOG_WITH_MASK;

  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/layers\/open\/dz2022-masked/i.test(url)) {
      await route.fulfill({
        status: maskStatus,
        contentType: "application/json",
        body:
          maskStatus === 200
            ? JSON.stringify(EMPTY_FC)
            : JSON.stringify({ detail: "not loaded" }),
      });
      return;
    }
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/parcels/i.test(url);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
    });
  });
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(catalog),
    });
  });
  await page.route("**/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(catalog),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layers: [
          {
            id: "demo",
            label: "Demo layer",
            developer_note:
              "Long developer note that would otherwise force horizontal scroll on narrow viewports when left unfolded.",
          },
        ],
      }),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/downloads/manifest.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        updated: "2026-10-15",
        bundles: [
          {
            id: "catalog",
            name: "Catalogue",
            whats_in_it: "Layer catalogue",
            format: "JSON",
            licence: "OGL-3.0",
            updated: "2026-10-15",
            file: null,
            bytes: null,
            api_anchor: "api-catalog",
            href: null,
          },
        ],
      }),
    });
  });
}

async function openLayers(page: Page) {
  const btn = page.getByTestId("hud-layers-btn");
  await expect(btn).toBeVisible({ timeout: 30_000 });
  if ((await page.getByTestId("layers-panel").count()) === 0) {
    await btn.click();
  }
  await expect(page.getByTestId("layers-panel")).toBeVisible({
    timeout: 15_000,
  });
}

async function openPlaceCard(page: Page) {
  await page.goto("/?lat=55.8609&lng=-4.2514");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await page.locator(".maplibregl-canvas").click({ position: { x: 400, y: 300 } });
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`WORDING-BATCH-1 map ${viewport.width}`, () => {
    test.use({ viewport });

    test("idea 55 OGL once; idea 57 mask copy; idea 41 Estimate chip", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);
      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await openLayers(page);

      const panel = page.getByTestId("layers-panel");
      await expect(panel.getByTestId("evidence-tag-legend-shadow")).toContainText(
        "Estimate",
      );
      await expect(panel).not.toContainText(/Estimate \(no market price\)/i);

      await expect(panel.getByTestId("layer-desc-builtup_mask")).toHaveText(
        MASK_COPY,
      );

      // Idea 55 — OGL once per group, not under every OGL layer row.
      const landOgl = panel.getByTestId("layers-group-ogl-land");
      await expect(landOgl).toBeVisible();
      await expect(landOgl).toContainText("Open Government Licence");
      await expect(panel.getByTestId("layer-licence-vdl")).toHaveCount(0);
      await expect(panel.getByTestId("layer-licence-1")).toHaveCount(0);
      await expect(
        panel.getByTestId("map-layers-sources-licences"),
      ).toContainText("Sources and licences");

      // Non-OGL still has a row licence (NSTA).
      await expect(panel.getByTestId("layer-licence-9")).toContainText(
        /North Sea Transition Authority/i,
      );

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });

    test("idea 57 Coming soon when mask tiles 503", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page, { maskStatus: 503 });
      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await openLayers(page);

      const toggle = page.getByTestId("layer-toggle-builtup_mask");
      await expect(toggle).toBeVisible({ timeout: 30_000 });
      // Toggle starts enabled; turning it on hits 503 → Coming soon / disabled.
      await expect(toggle).toBeEnabled();
      await toggle.click();
      await expect(
        page.getByTestId("layer-coming-soon-builtup_mask"),
      ).toHaveText("Coming soon", { timeout: 15_000 });
      await expect(toggle).toBeDisabled();
      await expect(page.getByTestId("map-layer-builtup_mask")).toHaveAttribute(
        "data-coming-soon",
        "true",
      );

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}

test.describe("WORDING-BATCH-1 place card + SW-047 (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("map reference, parts label, Why?, compact legend, value rows", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    const card = await openPlaceCard(page);

    await expect(card.getByTestId("place-card-map-reference")).toContainText(
      "Map reference",
    );
    await expect(card.getByTestId("place-card-square-reference")).toBeVisible();
    await expect(
      card.getByTestId("place-card-map-reference-copy"),
    ).toHaveText("Copy");
    await expect(card).not.toContainText(/Square reference/i);

    await expect(card.getByTestId("place-card-figure")).toContainText(PRE_POUND);
    await expect(
      card.getByTestId("place-card-land-values-coming-soon"),
    ).toHaveText(LAND_VALUES_COMING_SOON);

    await expect(card.getByTestId("place-card-figure-status")).toContainText(
      "Figure not published yet",
    );
    const why = card.getByTestId("place-card-figure-why");
    await expect(why).toHaveText("Why?");
    await expect(why).toHaveAttribute("href", "/methodology#how-sure");

    const parts = card.getByTestId("place-card-parts");
    await expect(parts.locator("summary")).toHaveText(PARTS_SUMMARY);
    await expect(card.getByTestId("place-tag-estimate").first()).toHaveText(
      "Estimate",
    );
    await expect(card).not.toContainText(/Estimate \(no market price\)/);

    const showLegend = page.getByRole("button", { name: "Show legend" });
    await showLegend.click();
    const legend = page.getByTestId("map-legend-panel");
    await expect(legend).toHaveAttribute("data-legend-compact", "true");
    await expect(legend.getByTestId("map-range-legend-title")).toBeVisible();
    await expect(legend.getByTestId("map-licence-credits")).toHaveCount(0);
    await expect(legend).not.toContainText(/Data licences/i);
    await expect(legend).not.toContainText(/Open Government Licence/i);

    const valueRows = card.getByTestId("place-card-value-rows");
    await expect(valueRows).toBeVisible();
    // SW-047: value rows live outside the scrollable sheet — fully painted.
    const valueBox = await valueRows.boundingBox();
    expect(valueBox, "value rows box").toBeTruthy();
    expect(valueBox!.height, "value-row height kept").toBeGreaterThan(20);
    const inSheet = await valueRows.evaluate((el) =>
      Boolean(el.closest(".place-card-sheet-body")),
    );
    expect(inSheet, "value rows not inside scrollable sheet").toBe(false);
    const rowScroll = await valueRows.evaluate((el) => ({
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
    }));
    expect(
      rowScroll.scrollHeight,
      "value rows list itself does not scroll",
    ).toBeLessThanOrEqual(rowScroll.clientHeight + 1);

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/£\d/);
    expect(bodyText).not.toMatch(BANNED);

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});

test.describe("WORDING-BATCH-1 place card (390)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("map reference, parts, Why?, Estimate chip", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    // Narrow: click near centre after goto with coords (map may auto-open).
    await page.goto("/?lat=55.8609&lng=-4.2514");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    const card = page.getByTestId("place-card");
    if ((await card.count()) === 0) {
      await page.locator(".maplibregl-canvas").click({
        position: { x: 195, y: 400 },
      });
    }
    await expect(card).toBeVisible({ timeout: 30_000 });

    await expect(card.getByTestId("place-card-map-reference")).toContainText(
      "Map reference",
    );
    await expect(card.getByTestId("place-card-figure")).toContainText(PRE_POUND);
    await expect(
      card.getByTestId("place-card-land-values-coming-soon"),
    ).toHaveText(LAND_VALUES_COMING_SOON);
    await expect(card.getByTestId("place-card-figure-why")).toHaveAttribute(
      "href",
      "/methodology#how-sure",
    );
    await expect(card.getByTestId("place-card-parts").locator("summary")).toHaveText(
      PARTS_SUMMARY,
    );
    await expect(card).not.toContainText(/£\d/);
    await expect(card).not.toContainText(BANNED);

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});

function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`WORDING-BATCH-1 addendum 17:40 ${viewport.width}`, () => {
    test.use({ viewport });

    test("A1 home coming-soon; A2 Rent? It; A4 postcode space; A5 legend pill", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await expect(page.getByTestId("land-values-coming-soon")).toHaveText(
        LAND_VALUES_COMING_SOON,
      );
      await expect(page.locator("body")).not.toContainText(/£\d/);
      await expect(page.locator("body")).not.toContainText(BANNED);

      await page.goto("/methodology");
      const agrDef = page.getByTestId("methodology-agr-definition");
      await expect(agrDef).toBeVisible();
      const agrText = await agrDef.innerText();
      expect(agrText).toMatch(/Rent\?\s+It/);
      expect(agrText).not.toMatch(/Rent\?It/);

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await page.route("**/backend/geocode/postcode**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            postcode: "EH11YZ",
            lat: 55.9533,
            lng: -3.1883,
            kind: "postcode_centroid",
          }),
        });
      });
      await page.route("**/backend/place**", async (route) => {
        const url = route.request().url();
        if (/[?&]q=/i.test(url)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ kind: "postcode", postcode: "EH11YZ" }),
          });
          return;
        }
        await route.continue();
      });
      await page.route("**/backend/postcode/**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            postcode: { postcode: "EH11YZ" },
            lat: 55.9533,
            lng: -3.1883,
            status: "location_only",
          }),
        });
      });
      await page.route("**/backend/platform/place**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(PLACE_STUB),
        });
      });

      const input = page.locator("#place-query");
      await input.fill("EH1 1YZ");
      await page.locator(".hud-search-go").click();
      await expect(page.getByTestId("place-card")).toBeVisible({
        timeout: 30_000,
      });
      await expect(input).toHaveValue("EH1 1YZ");

      const pill = page.getByRole("button", { name: "Show legend" });
      await expect(pill).toBeVisible({ timeout: 15_000 });
      const card = page.getByTestId("place-card");
      const pillBox = await pill.boundingBox();
      const cardBox = await card.boundingBox();
      expect(pillBox, "legend pill box").toBeTruthy();
      expect(cardBox, "place card box").toBeTruthy();
      expect(
        boxesOverlap(pillBox!, cardBox!),
        "SW-049: closed legend pill must not sit under the place card",
      ).toBe(false);
      await pill.click();
      await expect(page.locator(".hud-scotland.legend-open")).toBeVisible({
        timeout: 10_000,
      });

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });

    test("A3 SW-042 no-match × pad; 390 clears Layers", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);
      await page.route("**/backend/place**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ kind: "none", note: "No place matched" }),
        });
      });
      await page.route("**/backend/geocode/postcode**", async (route) => {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "not found" }),
        });
      });

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await page.locator("#place-query").fill("zzzznotaplace");
      await page.locator(".hud-search-go").click();

      const card = page.getByTestId("place-card");
      await expect(card).toBeVisible({ timeout: 30_000 });
      await expect(card).toHaveClass(/place-card-search-miss/);
      const text = page.getByTestId("place-card-no-match-text");
      await expect(text).toBeVisible();
      const close = page.getByRole("button", { name: "Close place card" });
      await expect(close).toBeVisible();

      await expect(async () => {
        const closeBox = await close.boundingBox();
        const textBox = await text.boundingBox();
        expect(closeBox).toBeTruthy();
        expect(textBox).toBeTruthy();
        const padRight = await page
          .locator(".place-card-no-match-line")
          .first()
          .evaluate((el) => parseFloat(getComputedStyle(el).paddingRight));
        expect(padRight).toBeGreaterThanOrEqual(closeBox!.width + 8 - 0.5);
        expect(
          boxesOverlap(closeBox!, textBox!),
          "SW-042: × must not overlap no-match text",
        ).toBe(false);
      }).toPass({ timeout: 15_000 });

      if (viewport.width === 390) {
        const layers = page.getByTestId("hud-layers-btn");
        await expect(layers).toBeVisible();
        const layersBox = await layers.boundingBox();
        const cardBox = await card.boundingBox();
        expect(layersBox).toBeTruthy();
        expect(cardBox).toBeTruthy();
        expect(
          boxesOverlap(cardBox!, layersBox!),
          "SW-042: no-match toast must not cover Layers at 390",
        ).toBe(false);
        const zoom = page.locator(".maplibregl-ctrl-zoom-in");
        if (await zoom.isVisible().catch(() => false)) {
          const zoomBox = await zoom.boundingBox();
          expect(zoomBox).toBeTruthy();
          expect(
            boxesOverlap(cardBox!, zoomBox!),
            "SW-042: no-match toast must not cover zoom at 390",
          ).toBe(false);
        }
      }

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}

test.describe("WORDING-BATCH-1 developers", () => {
  for (const viewport of [
    { width: 1280, height: 800 },
    { width: 390, height: 844 },
  ]) {
    test.describe(`${viewport.width}`, () => {
      test.use({ viewport });

      test("idea 26 Not packaged yet; SW-033 Scot-LAND API + folded notes", async ({
        page,
      }) => {
        test.setTimeout(90_000);
        const gate = attachConsoleGate(page);
        await stubMapBackend(page);

        await page.goto("/developers");
        await expect(
          page.getByTestId("download-size-catalog"),
        ).toHaveText("Not packaged yet");
        await expect(page.locator("body")).not.toContainText(/Size\s*—/);

        await page.route("**/backend/openapi.json", async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              openapi: "3.0.3",
              info: { title: "Scot-LAND API", version: "0.0.0-e2e" },
              paths: {
                "/health": {
                  get: {
                    summary: "Health",
                    responses: { "200": { description: "ok" } },
                  },
                },
              },
            }),
          });
        });

        await page.goto("/developers/api");
        await expect(page.getByTestId("api-reference-title")).toHaveText(
          "Scot-LAND API",
        );
        const notes = page.getByTestId("catalog-developer-notes");
        await expect(notes).toBeVisible();
        await expect(notes).not.toHaveAttribute("open", "");
        await expect(
          page.getByTestId("catalog-developer-notes-summary"),
        ).toHaveText("Catalogue technical notes");

        const noHScroll = await page.evaluate(() => {
          const root = document.documentElement;
          return root.scrollWidth <= root.clientWidth + 1;
        });
        expect(noHScroll, "no horizontal scroll").toBe(true);

        expect(filterNoise(gate.consoleErrors)).toEqual([]);
        expect(filterNoise(gate.pageErrors)).toEqual([]);
      });
    });
  }
});
