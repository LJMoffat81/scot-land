import { expect, test, type Page } from "@playwright/test";
import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * UI-TWEAKS-2 — mobile peek never covers the disclaimer.
 * 390×844 and 360×740. EH1 1YZ, IV27 4HN, Inverness.
 * Peek shows the place name, the Annual Ground Rent line, and the
 * disclaimer, each visible and unobscured. "More about this area" is
 * hidden in peek and visible in half. Asserts can fail.
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

function overlapSize(a: Box, b: Box): { x: number; y: number } {
  if (a.width <= 0 || a.height <= 0 || b.width <= 0 || b.height <= 0) {
    return { x: 0, y: 0 };
  }
  return {
    x: Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x),
    y: Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y),
  };
}

function boxesOverlap(a: Box, b: Box): boolean {
  const { x, y } = overlapSize(a, b);
  return x > 1 && y > 1;
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
    intermediate_zone: { status: "ok", name: label, code: "S02001607" },
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

async function openSearchedCard(page: Page, query: string) {
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
  await expect(slot).toHaveAttribute("data-detent", "half");
}

async function stepToPeek(page: Page) {
  const slot = page.getByTestId("map-panel-slot");
  const detent = await slot.getAttribute("data-detent");
  if (detent === "half") {
    await page.keyboard.press("Escape");
  } else if (detent === "full") {
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
  }
  await expect(slot).toHaveAttribute("data-detent", "peek");
}

async function textBox(locator: ReturnType<Page["getByTestId"]>): Promise<Box> {
  await expect(locator).toBeVisible();
  const box = await locator.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const r = range.getBoundingClientRect();
    const s = getComputedStyle(el);
    return {
      x: r.x,
      y: r.y,
      width: r.width,
      height: r.height,
      display: s.display,
      visibility: s.visibility,
    };
  });
  expect(box.display).not.toBe("none");
  expect(box.visibility).not.toBe("hidden");
  expect(box.width).toBeGreaterThan(0);
  expect(box.height).toBeGreaterThan(0);
  return box;
}

async function assertUnobscured(
  page: Page,
  locator: ReturnType<Page["getByTestId"]>,
  box: Box,
) {
  const slotBox = await page.getByTestId("map-panel-slot").boundingBox();
  expect(slotBox, "sheet box").toBeTruthy();
  expect(box.y).toBeGreaterThanOrEqual(slotBox!.y - 1);
  expect(box.x).toBeGreaterThanOrEqual(slotBox!.x - 1);
  expect(box.y + box.height).toBeLessThanOrEqual(slotBox!.y + slotBox!.height + 1);
  expect(box.x + box.width).toBeLessThanOrEqual(slotBox!.x + slotBox!.width + 1);

  const buttons = page.getByTestId("map-panel-slot").getByRole("button");
  const buttonCount = await buttons.count();
  for (let i = 0; i < buttonCount; i += 1) {
    const bb = await buttons.nth(i).boundingBox();
    if (!bb || bb.width <= 0 || bb.height <= 0) continue;
    expect(boxesOverlap(box, bb)).toBe(false);
  }

  const covers = await locator.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const r = range.getBoundingClientRect();
    const points = [
      [r.left + r.width / 2, r.top + r.height / 2],
      [r.left + Math.min(8, r.width / 2), r.top + r.height / 2],
    ];
    return points.map(([x, y]) => {
      const node = document.elementFromPoint(x, y);
      return {
        own: node === el || (node != null && el.contains(node)),
        tag: node?.tagName ?? null,
        testid: node?.getAttribute("data-testid") ?? null,
        text: (node?.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80),
      };
    });
  });
  for (const hit of covers) {
    expect(hit.own, JSON.stringify(hit)).toBe(true);
  }
}

async function assertHalfShowsFold(page: Page) {
  const slot = page.getByTestId("map-panel-slot");
  await expect(slot).toHaveAttribute("data-detent", "half");
  const parts = page.getByTestId("place-card-parts");
  await expect(parts).toHaveCount(1);
  await expect(parts).toBeVisible();
  const summary = parts.locator("summary");
  await expect(summary).toBeVisible();
  await expect(summary).toContainText("More about this area");
  await summary.evaluate((el) => {
    const scroller = el.closest(".map-panel-slot-scroll");
    if (!(scroller instanceof HTMLElement)) {
      el.scrollIntoView({ block: "center", inline: "nearest" });
      return;
    }
    const scrollerTop = scroller.getBoundingClientRect().top;
    const top = el.getBoundingClientRect().top;
    scroller.scrollTop += top - scrollerTop;
  });
  const mb = await summary.boundingBox();
  expect(mb, "More about this area box").toBeTruthy();
  expect(mb!.width).toBeGreaterThan(0);
  expect(mb!.height).toBeGreaterThan(0);
  const hit = await summary.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const x = r.left + r.width / 2;
    const y = r.top + r.height / 2;
    const node = document.elementFromPoint(x, y);
    return {
      own: node === el || (node != null && el.contains(node)),
      tag: node?.tagName ?? null,
      id: node?.id ?? null,
      testid: node?.getAttribute("data-testid") ?? null,
      text: (node?.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80),
      box: { x: r.x, y: r.y, width: r.width, height: r.height },
      point: { x, y },
    };
  });
  expect(hit.own, JSON.stringify(hit)).toBe(true);
}

async function assertPeekClear(page: Page, place: string) {
  const slot = page.getByTestId("map-panel-slot");
  await expect(slot).toHaveAttribute("data-detent", "peek");

  const name = page.getByTestId("place-card-place");
  await expect(name).toHaveText(place);
  const agr = page.getByTestId("place-card-agr-label");
  await expect(agr).toHaveText("Annual Ground Rent");
  const disclaimer = page.getByTestId("place-card-footer");
  await expect(disclaimer).toBeVisible();
  const position = await disclaimer.evaluate(
    (el) => getComputedStyle(el).position,
  );
  expect(position).toBe("static");

  const nameBox = await textBox(name);
  const agrBox = await textBox(agr);
  const disclaimerBox = await textBox(disclaimer);
  const stacked = overlapSize(nameBox, agrBox);
  // Line boxes share a few pixels of leading. A real cover is taller than that.
  expect(
    stacked.x > 1 && stacked.y > 4,
    JSON.stringify({ nameBox, agrBox }),
  ).toBe(false);
  expect(overlapSize(nameBox, disclaimerBox).y > 1).toBe(false);
  expect(overlapSize(agrBox, disclaimerBox).y > 1).toBe(false);
  await assertUnobscured(page, name, nameBox);
  await assertUnobscured(page, agr, agrBox);
  await assertUnobscured(page, disclaimer, disclaimerBox);

  const parts = page.getByTestId("place-card-parts");
  await expect(parts).toHaveCount(1);
  await expect(parts).toBeHidden();
  const summary = parts.locator("summary");
  await expect(summary).toHaveCount(1);
  await expect(summary).toContainText("More about this area");
  await expect(summary).toBeHidden();
  expect(await summary.boundingBox()).toBeNull();
  const folded = await parts.evaluate((el) => getComputedStyle(el).display);
  expect(folded).toBe("none");
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
        await openSearchedCard(page, place);
        await assertHalfShowsFold(page);
        await stepToPeek(page);
        await assertPeekClear(page, place);

        await page.setViewportSize({
          width: viewport.height,
          height: viewport.width,
        });
        await assertPeekClear(page, place);

        await page.setViewportSize({
          width: viewport.width,
          height: viewport.height,
        });
        await assertPeekClear(page, place);
      });
    }
  });
}
