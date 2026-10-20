import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * WORDING-BATCH-1 aligned with MAP-CARDS — no coming-soon banner spam,
 * builtup not a switch, §5 place copy, legend strip/inline, no-match under search.
 */

const BANNED =
  /\b(natural capital|ledger|headline|shadow|yield|what3words)\b/i;

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
      tag: "proxy",
      class: "proxy",
      status: "in_progress",
      applies: true,
      range: "not yet estimated",
    },
    {
      id: "resource",
      label: "Natural resource rents",
      tag: "market",
      class: "market",
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
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/boundaries\//i.test(url) ||
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
            id: "e2e-dev-note",
            label: "E2E sample layer",
            developer_note: "Ingest detail for SW-033 folded notes.",
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
  const card = page.getByTestId("place-card");
  if ((await card.count()) === 0) {
    await page.locator(".maplibregl-canvas").click({ position: { x: 400, y: 300 } });
  }
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`WORDING-BATCH-1 map ${viewport.width}`, () => {
    test.use({ viewport });

    test("Layers: sources link; builtup absent; no coming soon", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);
      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await openLayers(page);

      const panel = page.getByTestId("layers-panel");
      await expect(panel).not.toContainText(/coming soon/i);
      // LAYERS-NAV-1 placeholders use the roadmap tag "Coming later".
      // Live switches still must not.
      const switchText = await panel.getByRole("switch").allInnerTexts();
      for (const line of switchText) {
        expect(line).not.toMatch(/coming soon|coming later/i);
      }
      await expect(panel.getByTestId("layer-toggle-builtup_mask")).toHaveCount(0);
      await expect(
        panel.getByTestId("map-layers-sources-licences"),
      ).toContainText("Sources and licences");
      await expect(
        panel.getByTestId("map-layers-roadmap-link").locator("a"),
      ).toHaveAttribute("href", "/roadmap#map-layers");

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}

test.describe("WORDING-BATCH-1 place card + MAP-CARDS (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("§5 copy; no map reference; no Show legend; no land-values banner", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    const card = await openPlaceCard(page);

    await expect(card).not.toContainText(/map reference/i);
    await expect(card.getByTestId("place-card-map-reference")).toHaveCount(0);
    await expect(card.getByTestId("place-card-figure")).toContainText(PRE_POUND);
    await expect(card.getByTestId("place-card-figure-status")).toHaveText(
      "Not published yet",
    );
    await expect(card.getByTestId("place-card-land-values-coming-soon")).toHaveCount(
      0,
    );
    await expect(card.getByTestId("place-card-figure-why")).toHaveCount(0);
    await expect(card.getByTestId("place-card-parts").locator("summary")).toHaveText(
      "More about this area ▾",
    );

    await expect(page.getByRole("button", { name: "Show legend" })).toHaveCount(0);
    await expect(page.getByTestId("map-legend-panel")).toHaveCount(0);
    await expect(page.getByTestId("land-values-coming-soon")).toHaveCount(0);

    const bodyText = await page.locator("body").innerText();
    expect(bodyText).not.toMatch(/£\d/);
    expect(bodyText).not.toMatch(BANNED);

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});

test.describe("WORDING-BATCH-1 place card (390)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("§5 copy; no map reference; no Why?", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    await page.goto("/?lat=55.8609&lng=-4.2514");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    const card = page.getByTestId("place-card");
    if ((await card.count()) === 0) {
      await page.locator(".maplibregl-canvas").click({
        position: { x: 195, y: 400 },
      });
    }
    await expect(card).toBeVisible({ timeout: 30_000 });

    await expect(card).not.toContainText(/map reference/i);
    await expect(card.getByTestId("place-card-figure")).toContainText(PRE_POUND);
    await expect(card.getByTestId("place-card-figure-why")).toHaveCount(0);
    await expect(card.getByTestId("place-card-parts").locator("summary")).toHaveText(
      "More about this area ▾",
    );
    await expect(card).not.toContainText(/£\d/);
    await expect(card).not.toContainText(BANNED);

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`WORDING-BATCH-1 rest + methodology ${viewport.width}`, () => {
    test.use({ viewport });

    test("rest prompt; methodology Rent? It; postcode keeps space; no-match under search", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await expect(page.getByTestId("map-rest-prompt")).toHaveText(
        "Search a place or pick a layer.",
      );
      await expect(page.getByTestId("land-values-coming-soon")).toHaveCount(0);

      await page.goto("/methodology");
      const agrDef = page.getByTestId("methodology-agr-definition");
      await expect(agrDef).toBeVisible();
      const agrText = await agrDef.innerText();
      expect(agrText).toMatch(/Rent\?\s+It/);
      expect(agrText).not.toMatch(/Rent\?It/);

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await page.route("**/backend/place**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ kind: "places", matches: [] }),
        });
      });
      await page.locator("#place-query").fill("zzzznotaplace");
      await page.locator(".hud-search-go").click();
      await expect(page.getByTestId("search-no-match")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByTestId("place-card")).toHaveCount(0);

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

      test("idea 26 catalog size packaged; SW-033 Scot-LAND API + folded notes", async ({
        page,
      }) => {
        test.setTimeout(90_000);
        const gate = attachConsoleGate(page);
        await stubMapBackend(page);

        await page.goto("/developers");
        await expect(page.getByTestId("download-size-catalog")).toHaveText(
          /\d+(\.\d+)?\s*KB/,
        );
        await expect(page.locator("body")).not.toContainText(/Size\s*—/);

        await page.goto("/developers/api");
        await expect(page.getByRole("heading", { level: 1 })).toHaveText(
          "Developer API and bulk data: later",
        );
        await expect(page.getByTestId("catalog-developer-notes")).toHaveCount(0);
        await expect(page.getByTestId("api-register-interest")).toHaveCount(0);
        await expect(page.locator('a[href="/about#contact"]')).toHaveCount(0);

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

test.describe("WORDING-BATCH-1 deep-link vs Layers at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("late place boot leaves Sources and licences in Layers", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    let releaseStyle = () => {};
    const styleHeld = new Promise<void>((resolve) => {
      releaseStyle = resolve;
    });
    await page.route("**/tiles.openfreemap.org/styles/**", async (route) => {
      await styleHeld;
      await route.continue();
    });

    await page.goto("/?lat=55.8609&lng=-4.2514");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    await openLayers(page);
    const placeBoot = page.waitForRequest("**/platform/place**");
    releaseStyle();
    await placeBoot;

    const panel = page.getByTestId("layers-panel");
    await expect(panel).not.toContainText(/coming soon/i);
    await expect(panel.getByTestId("layer-toggle-builtup_mask")).toHaveCount(0);
    await expect(
      panel.getByTestId("map-layers-sources-licences"),
    ).toContainText("Sources and licences");
    await expect(
      panel.getByTestId("map-layers-roadmap-link").locator("a"),
    ).toHaveAttribute("href", "/roadmap#map-layers");

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});
