import { expect, test, type Page } from "@playwright/test";

/**
 * UI-TWEAKS-2 — mobile peek never covers the disclaimer.
 * 390×844 and 360×740. EH1 1YZ, IV27 4HN, Inverness.
 * Peek = name + rent + disclaimer. "More about this area" stays in
 * normal flow under the disclaimer. Asserts can fail.
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

function boxesOverlap(a: Box, b: Box): boolean {
  if (a.width <= 0 || a.height <= 0 || b.width <= 0 || b.height <= 0) return false;
  const x = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const y = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return x > 0 && y > 0;
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

async function openPeek(page: Page, query: string) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const input = page.locator("#place-query");
  await input.fill(query);
  await page.locator(".hud-search-go").click();
  const slot = page.getByTestId("map-panel-slot");
  await expect(slot).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("place-card-place")).toBeVisible({
    timeout: 30_000,
  });
  const detent = await slot.getAttribute("data-detent");
  if (detent === "half") {
    await page.keyboard.press("Escape");
  } else if (detent === "full") {
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
  }
  await expect(slot).toHaveAttribute("data-detent", "peek");
}

async function assertDisclaimerClear(page: Page) {
  const slot = page.getByTestId("map-panel-slot");
  await expect(slot).toHaveAttribute("data-detent", "peek");
  const disclaimer = page.getByTestId("place-card-footer");
  await expect(disclaimer).toBeVisible();
  const box = await disclaimer.boundingBox();
  expect(box, "disclaimer bounding box").toBeTruthy();
  expect(box!.width).toBeGreaterThan(0);
  expect(box!.height).toBeGreaterThan(0);

  const more = page.locator("summary", { hasText: "More about this area" });
  const moreCount = await more.count();
  expect(moreCount, "More about this area").toBeGreaterThan(0);
  for (let i = 0; i < moreCount; i += 1) {
    const mb = await more.nth(i).boundingBox();
    expect(mb, "More about this area box").toBeTruthy();
    expect(mb!.width).toBeGreaterThan(0);
    expect(mb!.height).toBeGreaterThan(0);
    expect(boxesOverlap(box!, mb!)).toBe(false);
    expect(mb!.y).toBeGreaterThanOrEqual(box!.y + box!.height - 1);
  }

  const buttons = slot.getByRole("button");
  const buttonCount = await buttons.count();
  for (let i = 0; i < buttonCount; i += 1) {
    const bb = await buttons.nth(i).boundingBox();
    if (!bb || bb.width <= 0 || bb.height <= 0) continue;
    expect(boxesOverlap(box!, bb)).toBe(false);
  }

  const covers = await disclaimer.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const node = document.elementFromPoint(x, y);
    const own = node === el || (node != null && el.contains(node));
    return {
      own,
      tag: node?.tagName ?? null,
      testid: node?.getAttribute("data-testid") ?? null,
      text: (node?.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80),
    };
  });
  expect(covers.own, JSON.stringify(covers)).toBe(true);
}

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 360, height: 740 },
] as const;

for (const viewport of VIEWPORTS) {
  test.describe(`UI-TWEAKS-2 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    for (const place of PLACES) {
      test(`${place} peek disclaimer stays clear`, async ({ page }) => {
        test.setTimeout(120_000);
        await stubMap(page);
        await openPeek(page, place);
        await assertDisclaimerClear(page);

        await page.setViewportSize({
          width: viewport.height,
          height: viewport.width,
        });
        await assertDisclaimerClear(page);

        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });
        await assertDisclaimerClear(page);
      });
    }
  });
}
