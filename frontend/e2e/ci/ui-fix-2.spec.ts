import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * UI-FIX-2 — mobile place-card layout after #173.
 * 390×844 and 1280×800. Opens a card by postcode/place search.
 * Asserts real boxes (0 px intersection) and counts, so a missing
 * control or a repeat of the attribution (i) fails.
 */

const PLACES = ["EH1 1YZ", "Inverness", "IV27 4HN"] as const;

const COORDS: Record<(typeof PLACES)[number], { lat: number; lng: number }> = {
  "EH1 1YZ": { lat: 55.9533, lng: -3.1883 },
  Inverness: { lat: 57.4778, lng: -4.2247 },
  "IV27 4HN": { lat: 58.419, lng: -4.762 },
};

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

type Box = { x: number; y: number; width: number; height: number };

function intersectionArea(a: Box, b: Box): number {
  const width = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const height = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  if (width <= 0 || height <= 0) return 0;
  return width * height;
}

async function visibleBox(locator: Locator, label: string): Promise<Box> {
  await expect(locator, label).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} box`).toBeTruthy();
  expect(box!.width, `${label} width`).toBeGreaterThan(0);
  expect(box!.height, `${label} height`).toBeGreaterThan(0);
  return box!;
}

async function assertClear(a: Locator, b: Locator, label: string) {
  const boxA = await visibleBox(a, `${label} A`);
  const boxB = await visibleBox(b, `${label} B`);
  expect(
    intersectionArea(boxA, boxB),
    `${label}: intersection a=${JSON.stringify(boxA)} b=${JSON.stringify(boxB)}`,
  ).toBe(0);
}

function cardFor(label: string, lat: number, lng: number) {
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: label,
    council_name: "Council",
    data_zone: {
      status: "ok",
      code: "S01008677",
      name: "Zone",
      vintage: 2022,
    },
    intermediate_zone: { status: "ok", name: "IZ", code: "S02001607" },
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
  };
}

async function stubMap(page: Page) {
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      const u = new URL(url);
      const lat = Number(u.searchParams.get("lat"));
      const hit =
        PLACES.map((name) => ({ name, ...COORDS[name] })).find(
          (p) => Math.abs(p.lat - lat) < 0.05,
        ) ?? { name: "EH1 1YZ", ...COORDS["EH1 1YZ"] };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(cardFor(hit.name, hit.lat, hit.lng)),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      const u = new URL(url);
      const q = u.searchParams.get("q") ?? "";
      const name = PLACES.find(
        (p) => p.toLowerCase() === q.trim().toLowerCase(),
      );
      const hit = name ? { name, ...COORDS[name] } : null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          hit
            ? { kind: "point", lat: hit.lat, lng: hit.lng, label: hit.name }
            : { kind: "places", matches: [] },
        ),
      });
      return;
    }
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
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await expect(page.locator(".maplibregl-ctrl-attrib-button")).toBeVisible({
    timeout: 30_000,
  });
}

async function openCardBySearch(page: Page, query: string) {
  const input = page.locator("#place-query");
  await input.fill(query);
  await page.locator(".hud-search-go").click();
  await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("place-card-place")).toBeVisible();
}

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1280, height: 800 },
] as const) {
  test.describe(`UI-FIX-2 layout ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("attribution once, chrome clear, no empty card block", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await stubMap(page);
      await openMap(page);

      await assertClear(
        page.getByTestId("map-rest-prompt"),
        page.getByTestId("research-banner"),
        "tip vs banner",
      );

      await page.getByTestId("hud-layers-btn").click();
      await expect(page.getByTestId("layers-panel")).toBeVisible();
      await assertClear(
        page.locator(".hud-search"),
        page.locator(".layers-panel-header .hud-tools-title"),
        "search bar vs Layers title",
      );
      await page.getByTestId("map-panel-slot-close").click();
      await expect(page.getByTestId("layers-panel")).toHaveCount(0);

      for (const [index, query] of PLACES.entries()) {
        await openCardBySearch(page, query);

        await expect(
          page.locator(".maplibregl-ctrl-attrib-button"),
          `attribution toggles after ${query}`,
        ).toHaveCount(1);

        const tiled = await page
          .locator(".maplibregl-ctrl-attrib-button")
          .evaluate((el) => getComputedStyle(el).backgroundRepeat);
        expect(tiled, `attribution (i) tiles after ${query}`).toBe("no-repeat");

        if (index >= 1) {
          await expect(
            page.locator(".maplibregl-ctrl-attrib"),
            `attribution controls after second card (${query})`,
          ).toHaveCount(1);
        }

        await assertClear(
          page.getByTestId("identify-at-centre"),
          page.getByTestId("map-attribution-line"),
          `centre vs attribution (${query})`,
        );
        await assertClear(
          page.getByTestId("basemap-switcher"),
          page.locator(".hud-search"),
          `Detailed vs search (${query})`,
        );
        await assertClear(
          page.getByTestId("basemap-switcher"),
          page.locator(".hud-top"),
          `Detailed vs top bar (${query})`,
        );

        if (viewport.width >= 1280) {
          await expect(
            page.getByRole("button", { name: "Close place card" }),
          ).toHaveCount(1);
          const trailing = await page.getByTestId("place-card").evaluate((el) => {
            const last = el.lastElementChild;
            if (!last) return { empty: true, height: 0 };
            const text = (last.textContent || "").replace(/\s+/g, " ").trim();
            const height = last.getBoundingClientRect().height;
            return { empty: text.length === 0, height };
          });
          expect(
            trailing.empty && trailing.height > 24,
            `empty trailing block h=${trailing.height}`,
          ).toBe(false);

          const slack = await page.evaluate(() => {
            const slot = document.querySelector('[data-testid="map-panel-slot"]');
            const card = document.querySelector('[data-testid="place-card"]');
            if (!slot || !card) return 999;
            const s = slot.getBoundingClientRect();
            const c = card.getBoundingClientRect();
            return s.bottom - c.bottom;
          });
          expect(slack, "empty block below the place card").toBeLessThanOrEqual(24);
        }
      }
    });
  });
}
