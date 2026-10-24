/**
 * ARCH-5c — level ladder negatives (N5c-1..3) and breadcrumb / data-level e2e (E5c-1).
 */
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  getMapZoom,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import {
  buildPlaceBreadcrumbs,
  formatDerivedFromSlot,
  levelFromZoom,
} from "../../lib/levelLadder";
import type { Page } from "@playwright/test";

registerOpenFreeMapFontStub();

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

function placeFixture() {
  return {
    contract: "place_card_v1",
    lat: 55.8609,
    lng: -4.2514,
    place_label: "Glasgow City Centre",
    council_name: "Glasgow City",
    dwellings: 410,
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
        status: "in_progress",
        applies: true,
      },
    ],
    constraints: [],
    layers: [],
    links: [],
  };
}

async function stubMapChrome(page: Page) {
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(placeFixture()),
      });
      return;
    }
    if (/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01014567",
          name: "City Centre South",
          vintage: 2022,
        }),
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
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
}

async function openPlaceViaCoords(page: Page) {
  await page.goto("/?lat=55.860900&lng=-4.251400");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
}

async function jumpToZoom(page: Page, zoom: number) {
  await page.evaluate((z) => {
    const map = (
      window as unknown as {
        __map?: {
          jumpTo(opts: { zoom: number; center?: [number, number] }): void;
        };
      }
    ).__map;
    if (!map?.jumpTo) throw new Error("window.__map missing");
    map.jumpTo({ zoom: z, center: [-4.2514, 55.8609] });
  }, zoom);
  await expect
    .poll(async () => getMapZoom(page), { timeout: 15_000 })
    .toBeCloseTo(zoom, 1);
}

async function ensureHalfDetent(page: Page) {
  const slot = page.getByTestId("map-panel-slot");
  const detent = await slot.getAttribute("data-detent");
  if (detent === "half") return;
  const handle = page.getByTestId("map-panel-handle");
  // peek → half (one click); full → half (one click via peek then half).
  for (let i = 0; i < 3; i++) {
    const cur = await slot.getAttribute("data-detent");
    if (cur === "half") return;
    await handle.click();
    await expect(slot).not.toHaveAttribute("data-detent", cur ?? "");
  }
  await expect(slot).toHaveAttribute("data-detent", "half");
}

test("N5c-1 levelFromZoom", () => {
  expect(() => levelFromZoom()).toThrowError(
    /^LEVEL-LADDER: zoom must be a finite number$/,
  );
  for (const bad of [
    undefined,
    null,
    "",
    "6",
    NaN,
    Infinity,
    -Infinity,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => levelFromZoom(bad)).toThrowError(
      /^LEVEL-LADDER: zoom must be a finite number$/,
    );
  }

  for (const outOfRange of [-0.01, -1, -100, 22.01, 23, 100]) {
    expect(() => levelFromZoom(outOfRange)).toThrowError(
      /^LEVEL-LADDER: zoom must be between 0 and 22$/,
    );
  }

  expect(levelFromZoom(0)).toBe("scotland");
  expect(levelFromZoom(5.99)).toBe("scotland");
  expect(levelFromZoom(6)).toBe("council");
  expect(levelFromZoom(8.99)).toBe("council");
  expect(levelFromZoom(9)).toBe("dz2022");
  expect(levelFromZoom(13.99)).toBe("dz2022");
  expect(levelFromZoom(14)).toBe("parcel");
  expect(levelFromZoom(17.99)).toBe("parcel");
  expect(levelFromZoom(18)).toBe("square3m");
  expect(levelFromZoom(22)).toBe("square3m");
});

test("N5c-2 buildPlaceBreadcrumbs", () => {
  expect(() => buildPlaceBreadcrumbs()).toThrowError(
    /^LEVEL-LADDER: options must be an object$/,
  );
  for (const badOpts of [
    undefined,
    null,
    "",
    "str",
    123,
    1.5,
    true,
    false,
    [],
  ]) {
    expect(() => buildPlaceBreadcrumbs(badOpts)).toThrowError(
      /^LEVEL-LADDER: options must be an object$/,
    );
  }

  for (const badField of [123, 1.5, true, false, [], {}]) {
    expect(() =>
      buildPlaceBreadcrumbs({ councilName: badField }),
    ).toThrowError(
      /^LEVEL-LADDER: councilName must be a string or null\/undefined$/,
    );
    expect(() =>
      buildPlaceBreadcrumbs({ placeName: badField }),
    ).toThrowError(
      /^LEVEL-LADDER: placeName must be a string or null\/undefined$/,
    );
  }

  expect(buildPlaceBreadcrumbs({})).toEqual([
    { level: "scotland", label: "Scotland" },
  ]);
  expect(
    buildPlaceBreadcrumbs({
      councilName: "Glasgow City",
      placeName: "City Centre",
    }),
  ).toEqual([
    { level: "scotland", label: "Scotland" },
    { level: "council", label: "Glasgow City" },
    { level: "dz2022", label: "City Centre" },
  ]);
});

test("N5c-3 formatDerivedFromSlot", () => {
  expect(formatDerivedFromSlot()).toBe("");
  expect(formatDerivedFromSlot(undefined)).toBe("");
  expect(formatDerivedFromSlot(null)).toBe("");

  for (const badArr of ["dz2022", "", 123, 1.5, true, false, {}]) {
    expect(() => formatDerivedFromSlot(badArr)).toThrowError(
      /^LEVEL-LADDER: derivedFrom must be an array of strings$/,
    );
  }

  for (const badItem of [
    undefined,
    null,
    "",
    "  ",
    "DZ2022",
    "bad_slug",
    "bad slug",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => formatDerivedFromSlot([badItem])).toThrowError(
      /^LEVEL-LADDER: derivedFrom items must be non-empty slugs$/,
    );
  }

  expect(formatDerivedFromSlot(["dz2022"])).toBe("dz2022");
  expect(formatDerivedFromSlot(["dz2022", "parcel"])).toBe("dz2022,parcel");
});

async function runE5c1(page: Page, mobile: boolean) {
  test.setTimeout(120_000);
  const gate = attachConsoleGate(page);
  await stubMapChrome(page);
  await openPlaceViaCoords(page);

  if (mobile) {
    await ensureHalfDetent(page);
  }

  await expect(page.getByTestId("place-card-council")).toHaveText(
    "Glasgow City",
  );
  const crumb = page.getByTestId("place-card-crumb-scotland");
  await expect(crumb).toBeVisible();
  await expect(crumb).toHaveText("Scotland");
  const crumbBox = await crumb.boundingBox();
  expect(crumbBox).toBeTruthy();
  expect(crumbBox!.width).toBeGreaterThanOrEqual(44);
  expect(crumbBox!.height).toBeGreaterThanOrEqual(44);

  const derived = page.getByTestId("place-card-derived-from");
  await expect(derived).toBeHidden();
  await expect(derived).toHaveAttribute("data-derived-from", "dz2022");

  await jumpToZoom(page, 5);
  await expect(page.getByTestId("place-card")).toHaveAttribute(
    "data-level",
    "scotland",
  );
  await jumpToZoom(page, 7);
  await expect(page.getByTestId("place-card")).toHaveAttribute(
    "data-level",
    "council",
  );
  await jumpToZoom(page, 11);
  await expect(page.getByTestId("place-card")).toHaveAttribute(
    "data-level",
    "dz2022",
  );

  await crumb.click();
  await expect(page.getByTestId("place-card")).toHaveCount(0);
  await expect
    .poll(async () => getMapZoom(page), { timeout: 20_000 })
    .toBeLessThanOrEqual(7.5);

  assertConsoleClean(gate);
}

test.describe("E5c-1 level ladder UX desktop 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("E5c-1 breadcrumb, data-level, derived_from, Scotland reset", async ({
    page,
  }) => {
    await runE5c1(page, false);
  });
});

test.describe("E5c-1 level ladder UX mobile 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("E5c-1 breadcrumb, data-level, derived_from, Scotland reset", async ({
    page,
  }) => {
    await runE5c1(page, true);
  });
});
