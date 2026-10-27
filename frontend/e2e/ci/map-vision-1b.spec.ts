/**
 * MAP-VISION-1b (MV-28, MV-29, MV-1b-DEFAULT-OPEN, MV-1b-DZ-KEY / W-1b-1 & W-1b-2):
 * Unit + negative tests for mapUrlState.ts & assertNoBareNumericLegendLabels,
 * plus Playwright e2e verification on desktop (1280x800) and mobile (390x844).
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import {
  DZ2022_DENSITY_CLASSES,
  MAP_LAYER_REGISTRY,
  assertNoBareNumericLegendLabels,
  defaultOnLayerIds,
} from "../../lib/mapLayerRegistry";
import {
  buildShareableMapUrl,
  parseBasemapParam,
  parseMeasureParam,
  readMapUrlState,
  validateBasemapParam,
  validateMeasureParam,
  writeMapUrlSearch,
} from "../../lib/mapUrlState";
import {
  PLACE_CARD_SHARE_ARIA_LABEL,
  PLACE_CARD_SHARE_COPIED_ARIA_LABEL,
  PLACE_CARD_SHARE_COPIED_LABEL,
  PLACE_CARD_SHARE_LABEL,
} from "../../lib/placeCard";
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

async function stubPlaceBackend(page: Page) {
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
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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

async function ensureHalfDetent(page: Page) {
  const slot = page.getByTestId("map-panel-slot");
  const detent = await slot.getAttribute("data-detent");
  if (detent === "half") return;
  const handle = page.getByTestId("map-panel-handle");
  for (let i = 0; i < 3; i++) {
    const cur = await slot.getAttribute("data-detent");
    if (cur === "half") return;
    await handle.click();
    await expect(slot).not.toHaveAttribute("data-detent", cur ?? "");
  }
  await expect(slot).toHaveAttribute("data-detent", "half");
}

test("N-MV1b-1 validateBasemapParam, validateMeasureParam, buildShareableMapUrl positive & negative checks", () => {
  expect(validateBasemapParam("light")).toBe("light");
  expect(validateBasemapParam("simple")).toBe("light");
  expect(validateBasemapParam("aerial")).toBe("aerial");
  expect(parseBasemapParam(null)).toBe("light");
  expect(parseBasemapParam("invalid")).toBe("light");

  for (const bad of [undefined, null, "", "   ", 123, 1.5, true, false, [], {}]) {
    expect(() => validateBasemapParam(bad)).toThrow(
      /^MAP-URL: basemap must be 'light' or 'aerial'$/,
    );
  }
  for (const badStr of ["dark", "satellite", "terrain"]) {
    expect(() => validateBasemapParam(badStr)).toThrow(
      new RegExp(`^MAP-URL: invalid basemap '${badStr}'$`),
    );
  }

  expect(validateMeasureParam("pop_density")).toBe("pop_density");
  expect(validateMeasureParam("simd")).toBe("simd");
  expect(validateMeasureParam("house_price")).toBe("house_price");
  expect(validateMeasureParam("land_share")).toBe("land_share");
  expect(parseMeasureParam(null)).toBe("pop_density");
  expect(parseMeasureParam("bogus")).toBe("pop_density");

  for (const bad of [undefined, null, "", "   ", 123, 1.5, true, false, [], {}]) {
    expect(() => validateMeasureParam(bad)).toThrow(
      /^MAP-URL: measure must be a non-empty string$/,
    );
  }
  for (const badStr of ["agr_plot", "rent_per_sqm", "unknown"]) {
    expect(() => validateMeasureParam(badStr)).toThrow(
      new RegExp(`^MAP-URL: invalid measure '${badStr}'$`),
    );
  }

  expect(
    buildShareableMapUrl(
      "https://scot-land.scot/?c=-3.18827,55.95331&z=12&b=aerial&m=simd&l=9,vdl",
    ),
  ).toBe(
    "https://scot-land.scot/?layers=9%2Cvdl&b=aerial&m=simd&z=12&c=-3.18827%2C55.95331",
  );

  for (const badHref of [
    undefined,
    null,
    "",
    "   ",
    "not-a-valid-url",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => buildShareableMapUrl(badHref)).toThrow(
      /^MAP-URL: href must be a valid URL string$/,
    );
  }
});

test("N-MV1b-2 readMapUrlState & writeMapUrlSearch round-trip b=, m=, l= / layers=", () => {
  const s = readMapUrlState("?b=aerial&m=simd&l=9,councils&z=7&c=-3.20000,56.00000");
  expect(s.b).toBe("aerial");
  expect(s.m).toBe("simd");
  expect(s.layers).toEqual(["9", "councils"]);
  expect(s.l).toEqual(["9", "councils"]);
  expect(s.z).toBe(7);
  expect(s.center).toEqual({ lng: -3.2, lat: 56 });

  const written = writeMapUrlSearch({
    href: "http://local/",
    b: "aerial",
    m: "simd",
    l: ["9", "councils"],
    z: 7,
    center: { lng: -3.2, lat: 56 },
  });
  const round = readMapUrlState(written);
  expect(round.b).toBe("aerial");
  expect(round.m).toBe("simd");
  expect(round.layers).toEqual(["9", "councils"]);
  expect(round.l).toEqual(["9", "councils"]);
});

test("N-MV1b-3 assertNoBareNumericLegendLabels & defaultOnLayerIds & W-1b-1 legend pins", () => {
  expect(defaultOnLayerIds()).toEqual(["data_zones"]);
  const dzEntry = MAP_LAYER_REGISTRY.find((e) => e.id === "data_zones");
  expect(dzEntry?.minzoom).toBe(0);
  expect(dzEntry?.defaultOn).toBe(true);
  expect(dzEntry?.classes).toEqual(DZ2022_DENSITY_CLASSES);
  expect(DZ2022_DENSITY_CLASSES.map((c) => c.label)).toEqual([
    "Up to 10 people per km²",
    "10–100 people per km²",
    "100–500 people per km²",
    "500–1,500 people per km²",
    "1,500–3,000+ people per km²",
    "No value",
  ]);
  const councilsEntry = MAP_LAYER_REGISTRY.find((e) => e.id === "councils");
  expect(councilsEntry?.defaultOn).toBe(false);

  expect(() => assertNoBareNumericLegendLabels()).not.toThrow();

  // Also scan every committed backend/layers/registry/*.yaml legend label
  const regDir = join(__dirname, "..", "..", "..", "backend", "layers", "registry");
  const yamlFiles = readdirSync(regDir).filter((f) => f.endsWith(".yaml"));
  expect(yamlFiles.length).toBeGreaterThanOrEqual(7);
  for (const file of yamlFiles) {
    const text = readFileSync(join(regDir, file), "utf-8");
    const labelMatches = [...text.matchAll(/label:\s*"?([^"\n}]+)"?/g)];
    expect(labelMatches.length, file).toBeGreaterThanOrEqual(1);
    for (const m of labelMatches) {
      const lbl = m[1]!.trim();
      expect(/^\d+([.,]\d+)?$/.test(lbl), `${file}: bare numeric label ${lbl}`).toBe(
        false,
      );
    }
  }

  for (const badEntries of [null, "", 123, true, false, {}, []]) {
    expect(() => assertNoBareNumericLegendLabels(badEntries)).toThrow(
      /^REGISTRY-LEGEND: entries must be a non-empty array$/,
    );
  }
  for (const badEntry of [null, "str", 123, true, []]) {
    expect(() => assertNoBareNumericLegendLabels([badEntry])).toThrow(
      /^REGISTRY-LEGEND: entry must be an object$/,
    );
  }
  for (const badId of [undefined, null, "", "   ", 123, true]) {
    expect(() =>
      assertNoBareNumericLegendLabels([
        { id: badId, classes: [{ label: "Ok", color: "#000000" }] },
      ]),
    ).toThrow(/^REGISTRY-LEGEND: entry id must be a non-empty string$/);
  }
  expect(() =>
    assertNoBareNumericLegendLabels([{ id: "x", classes: "not-array" }]),
  ).toThrow(/^REGISTRY-LEGEND: 'x': classes must be an array$/);
  expect(() =>
    assertNoBareNumericLegendLabels([{ id: "x", classes: [null] }]),
  ).toThrow(/^REGISTRY-LEGEND: 'x': legend item must be an object$/);
  expect(() =>
    assertNoBareNumericLegendLabels([{ id: "x", classes: [{ label: "   " }] }]),
  ).toThrow(/^REGISTRY-LEGEND: 'x': legend label must be a non-empty string$/);

  for (const bare of ["0", "10", "100", "500", "1500", "3000", "12.5"]) {
    expect(() =>
      assertNoBareNumericLegendLabels([
        { id: "dz2022", classes: [{ label: bare, color: "#6baed6" }] },
      ]),
    ).toThrow(
      new RegExp(
        `^REGISTRY-LEGEND: 'dz2022': bare numeric legend label '${bare.replace(".", "\\.")}'$`,
      ),
    );
  }
});

for (const vp of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`E-MV1b MAP-VISION-1b @ ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: vp });

    test("MV-1b-DEFAULT-OPEN & MV-1b-DZ-KEY: data_zones default ON with people/km² key at low zoom and councils OFF", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await openMap(page, "/");
      await openLayers(page);
      await ensureLayersGroupOpen(page, "places");

      await expect(page.getByTestId("layer-toggle-data_zones")).toHaveAttribute(
        "aria-checked",
        "true",
      );
      await expect(page.getByTestId("layer-toggle-councils")).toHaveAttribute(
        "aria-checked",
        "false",
      );

      const dzLegend = page.getByTestId("layer-inline-legend-data_zones");
      await expect(dzLegend).toBeVisible();
      await expect(dzLegend).toContainText("Up to 10 people per km²");
      await expect(dzLegend).toContainText("1,500–3,000+ people per km²");
      await expect(dzLegend).not.toContainText("Zoom in to see this layer");

      assertConsoleClean(gate);
    });

    test("MV-28 & MV-29: Share button >=44x44 copies shareable URL and shows Copied / Link copied", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await page.addInitScript(() => {
        Object.defineProperty(navigator, "clipboard", {
          configurable: true,
          value: {
            writeText: async (text: string) => {
              (window as unknown as { __copiedUrl?: string }).__copiedUrl = text;
            },
          },
        });
      });
      await stubPlaceBackend(page);
      await page.goto("/?lat=55.860900&lng=-4.251400");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      const card = page.getByTestId("place-card");
      await expect(card).toBeVisible({ timeout: 45_000 });

      if (vp.width <= 900) {
        await ensureHalfDetent(page);
      }

      const shareBtn = card.getByTestId("place-card-share");
      await expect(shareBtn).toBeVisible();
      await expect(shareBtn).toHaveText(PLACE_CARD_SHARE_LABEL);
      await expect(shareBtn).toHaveAttribute(
        "aria-label",
        PLACE_CARD_SHARE_ARIA_LABEL,
      );

      const box = await shareBtn.boundingBox();
      expect(box, "place-card-share boundingBox").toBeTruthy();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);

      await shareBtn.click();
      await expect(shareBtn).toHaveText(PLACE_CARD_SHARE_COPIED_LABEL);
      await expect(shareBtn).toHaveAttribute(
        "aria-label",
        PLACE_CARD_SHARE_COPIED_ARIA_LABEL,
      );

      const copied = await page.evaluate(
        () => (window as unknown as { __copiedUrl?: string }).__copiedUrl ?? "",
      );
      expect(copied).toMatch(/^https?:\/\//);
      expect(copied).toContain("layers=");
      expect(copied).toContain("c=-4.25140%2C55.86090");

      assertConsoleClean(gate);
    });
  });
}
