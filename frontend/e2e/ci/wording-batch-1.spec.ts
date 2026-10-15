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

const PARTS_SUMMARY = "Natural resource rents & services of nature";

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
      await expect(toggle).toBeDisabled();
      await expect(
        page.getByTestId("layer-coming-soon-builtup_mask"),
      ).toHaveText("Coming soon");
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
    const scroll = await valueRows.evaluate((el) => {
      const host =
        el.closest(".place-card-sheet-body") ||
        el.closest(".place-card-body") ||
        el;
      return {
        scrollHeight: host.scrollHeight,
        clientHeight: host.clientHeight,
      };
    });
    expect(
      scroll.scrollHeight,
      "value rows must not need inner scrolling",
    ).toBeLessThanOrEqual(scroll.clientHeight + 1);

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
