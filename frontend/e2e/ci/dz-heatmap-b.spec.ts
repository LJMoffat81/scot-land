/**
 * DZ-HEATMAP PR-B — estimate-status fill + key on the dz2011 registry tileset.
 * Auto-discovered under e2e/ci/. Synthetic fixtures only: the dz2011 tiles are
 * the committed synthetic ARCH-2b square (feature_id S01013482); every payload
 * is built here. Each negative test changes exactly one thing.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test, routeManifestOverride } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import {
  DZ_STATUS_BOUNDARY_CREDIT,
  DZ_STATUS_CATEGORIES,
  DZ_STATUS_CREDIT,
  DZ_STATUS_DEFAULT_ON,
  DZ_STATUS_FILL_ID,
  DZ_STATUS_KEY_TITLE,
  DZ_STATUS_ROUTE,
  DZ_STATUS_VINTAGE_NOTE,
  dzStatusFillColor,
  dzStatusTiles,
  parseDzStatusPayload,
} from "../../lib/dzStatusLayer";
import { LAND_WORTH_CIVIDIS } from "../../lib/mapActiveLegend";
import type { TileManifest } from "../../lib/tileLayerFactory";

registerOpenFreeMapFontStub();

const FIXTURES = join(process.cwd(), "e2e", "fixtures", "arch2b");
const SQUARE_MVT = readFileSync(join(FIXTURES, "dz2022.mvt"));
const VERSION = "2026-11-05.0b0b0b0b";
const ROUTE_PATH = `/backend${DZ_STATUS_ROUTE}`;
const SYN_CODE = "S01013482";

const LOCKED_LABELS = [
  "Estimate available",
  "No estimate: data not available",
  "No estimate: our method doesn't work well here",
  "No estimate: too few similar sales",
  "No estimate: outside the areas we estimate",
];
const PROPOSED_CREDIT =
  "Scot-LAND estimate, not official data. Boundaries: Scottish Government, Data Zone Boundaries 2011, Open Government Licence v3.0";

function manifest(withDz2011 = true): TileManifest {
  return {
    schema: 1,
    tilesets: withDz2011
      ? {
          dz2011: {
            layer: "dz2011",
            version: VERSION,
            minzoom: 0,
            maxzoom: 14,
            geometry: "polygon",
            title: "Data Zones 2011",
            // Synthetic square fixture carries its layer name.
            source_layer: "dz2022",
            measure: null,
            attribution: "Synthetic dz2011 attribution",
            style: {},
            legend: [{ label: "Data Zone 2011 boundary", color: "#0b1e3a" }],
          },
        }
      : {},
  };
}

/** Valid PR-A payload, synthetic statuses: one per category, then the fixture code. */
function payload(): Record<string, unknown> {
  return {
    layer_id: "dz_status",
    data_zone_vintage: "DZ2011",
    estimate_year: 2024,
    key_title: "Estimate status",
    categories: [
      { id: "estimated", label: LOCKED_LABELS[0] },
      { id: "unavailable", label: LOCKED_LABELS[1] },
      { id: "model_failure", label: LOCKED_LABELS[2] },
      { id: "no_cell", label: LOCKED_LABELS[3] },
      { id: "not_scored", label: LOCKED_LABELS[4] },
    ],
    source: {
      credit: DZ_STATUS_BOUNDARY_CREDIT,
      licence: "Open Government Licence v3.0",
      attribution: "Synthetic attribution",
    },
    vintage_note: "Uses 2011 local areas (data zones)",
    zones: [
      { code: "S01000001", status: "unavailable" },
      { code: "S01000002", status: "model_failure" },
      { code: "S01000003", status: "no_cell" },
      { code: "S01000004", status: "not_scored" },
      { code: SYN_CODE, status: "estimated" },
    ],
  };
}

function refusal(raw: unknown): string {
  try {
    parseDzStatusPayload(raw);
  } catch (err: unknown) {
    if (err instanceof Error && err.name === "DzStatusRefused") return err.message;
    throw err;
  }
  return "accepted";
}

const R = "DZ-STATUS: REFUSED: ";

// ---------------------------------------------------------------- unit (no page)

test.describe("DZ-HEATMAP PR-B contract", () => {
  test("U-01 locked strings exact", () => {
    expect(DZ_STATUS_KEY_TITLE).toBe("Estimate status");
    expect(DZ_STATUS_CATEGORIES.map((c) => c.label)).toEqual(LOCKED_LABELS);
    expect(DZ_STATUS_CATEGORIES.map((c) => c.id)).toEqual([
      "estimated",
      "unavailable",
      "model_failure",
      "no_cell",
      "not_scored",
    ]);
    expect(DZ_STATUS_VINTAGE_NOTE).toBe("Uses 2011 local areas (data zones)");
    expect(DZ_STATUS_CREDIT).toBe(PROPOSED_CREDIT);
    expect(DZ_STATUS_ROUTE).toBe("/platform/dz-status");
  });

  test("U-02 layer is OFF by default", () => {
    expect(DZ_STATUS_DEFAULT_ON).toBe(false);
  });

  test("U-03 valid payload accepted", () => {
    expect(refusal(payload())).toBe("accepted");
  });

  test("U-04 fill colour matches feature_id by status", () => {
    const expr = dzStatusFillColor(parseDzStatusPayload(payload()));
    expect(expr).toEqual([
      "match",
      ["get", "feature_id"],
      [SYN_CODE],
      "#00224e",
      ["S01000001"],
      "#bdbdbd",
      ["S01000002"],
      "#969696",
      ["S01000003"],
      "#737373",
      ["S01000004"],
      "#d9d9d9",
      "rgba(0,0,0,0)",
    ]);
  });

  test("U-04b fill colours: category 1 cividis, categories 2-5 neutral greys", () => {
    expect(DZ_STATUS_CATEGORIES.map((c) => [c.id, c.color])).toEqual([
      ["estimated", "#00224e"],
      ["unavailable", "#bdbdbd"],
      ["model_failure", "#969696"],
      ["no_cell", "#737373"],
      ["not_scored", "#d9d9d9"],
    ]);
    expect(DZ_STATUS_CATEGORIES[0].color).toBe(LAND_WORTH_CIVIDIS[0]);
    const greys = DZ_STATUS_CATEGORIES.slice(1).map((c) => c.color);
    for (const g of greys) {
      expect(g).toMatch(/^#([0-9a-f]{2})\1\1$/);
    }
    expect(new Set(greys).size).toBe(4);
  });

  test("U-05 no dz2011 tileset → no source", () => {
    expect(dzStatusTiles(manifest(false))).toBeNull();
  });

  test("U-06 dz2011 source comes from the registry tile factory", () => {
    const t = dzStatusTiles(manifest(true));
    expect(t?.sourceLayer).toBe("dz2022");
    expect(t?.source.tiles).toEqual([
      `/backend/v1/tiles/dz2011/${VERSION}/{z}/{x}/{y}.mvt`,
    ]);
    expect(t?.source.promoteId).toBe("feature_id");
  });

  const NEG: Array<[string, (p: Record<string, unknown>) => unknown, string]> = [
    ["not object", () => [], "payload: expected object"],
    ["pound sign", (p) => ({ ...p, vintage_note: "\u00a31" }), "payload contains a pound sign"],
    ["gbp text", (p) => ({ ...p, source: { ...(p.source as object), licence: "GBP" } }), "payload contains a pound sign"],
    ["extra key value", (p) => ({ ...p, value: 1 }), "payload keys do not match contract"],
    ["missing key zones", (p) => { const q = { ...p }; delete q.zones; return q; }, "payload keys do not match contract"],
    ["layer_id", (p) => ({ ...p, layer_id: "dz_value" }), "layer_id: expected dz_status"],
    ["vintage DZ2022", (p) => ({ ...p, data_zone_vintage: "DZ2022" }), "data_zone_vintage: expected DZ2011"],
    ["year 2023", (p) => ({ ...p, estimate_year: 2023 }), "estimate_year 2023 is never shown"],
    ["year 2025", (p) => ({ ...p, estimate_year: 2025 }), "estimate_year: expected 2024"],
    ["year string", (p) => ({ ...p, estimate_year: "2024" }), "estimate_year: expected 2024"],
    ["key title", (p) => ({ ...p, key_title: "Estimate Status" }), "key_title: expected locked title"],
    ["label changed", (p) => ({ ...p, categories: (p.categories as Array<Record<string, string>>).map((c, i) => (i === 2 ? { ...c, label: "No estimate: method unreliable" } : c)) }), "categories: expected locked ids and labels"],
    ["category order", (p) => ({ ...p, categories: [...(p.categories as unknown[])].reverse() }), "categories: expected locked ids and labels"],
    ["category extra key", (p) => ({ ...p, categories: (p.categories as Array<Record<string, string>>).map((c, i) => (i === 0 ? { ...c, hint: "x" } : c)) }), "categories: expected locked ids and labels"],
    ["category id swapped", (p) => ({ ...p, categories: (p.categories as Array<Record<string, string>>).map((c, i) => (i === 0 ? { ...c, id: "unavailable" } : c)) }), "categories: expected locked ids and labels"],
    ["category dropped", (p) => ({ ...p, categories: (p.categories as unknown[]).slice(0, 4) }), "categories: expected locked ids and labels"],
    ["source extra key", (p) => ({ ...p, source: { ...(p.source as object), note: "x" } }), "source keys do not match contract"],
    ["source credit DZ2022", (p) => ({ ...p, source: { ...(p.source as object), credit: "Scottish Government, Data Zone Boundaries 2022, Open Government Licence v3.0" } }), "source.credit: expected DZ2011 boundary credit"],
    ["vintage note", (p) => ({ ...p, vintage_note: null }), "vintage_note: expected locked note"],
    ["zones empty", (p) => ({ ...p, zones: [] }), "zones: expected non-empty list"],
    ["zone extra key band", (p) => ({ ...p, zones: [{ code: SYN_CODE, status: "estimated", band: 3 }] }), "zone row keys do not match contract"],
    ["zone code English", (p) => ({ ...p, zones: [{ code: "E01000001", status: "estimated" }] }), "zone code: expected DZ2011 code"],
    ["zone duplicate", (p) => ({ ...p, zones: [{ code: SYN_CODE, status: "estimated" }, { code: SYN_CODE, status: "no_cell" }] }), `zone ${SYN_CODE}: duplicate`],
    ["zone unknown status", (p) => ({ ...p, zones: [{ code: SYN_CODE, status: "value" }] }), `zone ${SYN_CODE}: unknown status`],
    ["zone null status", (p) => ({ ...p, zones: [{ code: SYN_CODE, status: null }] }), `zone ${SYN_CODE}: unknown status`],
  ];
  for (const [name, mutate, msg] of NEG) {
    test(`N-${name}`, () => {
      expect(refusal(mutate(payload()))).toBe(`${R}${msg}`);
    });
  }
});

// ---------------------------------------------------------------- browser

type Mode = "ok" | "404" | "500" | "malformed" | "refused";

async function routeDzStatus(page: Page, mode: Mode, opts: { dz2011?: boolean } = {}) {
  const hits = { status: 0, urls: [] as string[] };
  page.on("request", (req) => hits.urls.push(req.url()));
  await routeManifestOverride(page, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(manifest(opts.dz2011 ?? true)),
    }),
  );
  await page.route("**/backend/v1/tiles/dz2011/**/*.mvt", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: SQUARE_MVT,
    }),
  );
  await page.route(
    (url) => url.pathname === ROUTE_PATH,
    async (route) => {
      hits.status += 1;
      // 404/500 carry an otherwise valid body so only the status can refuse.
      if (mode === "404") {
        await route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify(payload()) });
      } else if (mode === "500") {
        await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify(payload()) });
      } else if (mode === "malformed") {
        await route.fulfill({ status: 200, contentType: "application/json", body: "{" });
      } else if (mode === "refused") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...payload(), estimate_year: 2023 }) });
      } else {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload()) });
      }
    },
  );
  return hits;
}

async function fillState(page: Page): Promise<{ layer: boolean; rendered: number }> {
  return page.evaluate((id) => {
    const map = (
      window as unknown as {
        __map?: {
          getLayer: (id: string) => unknown;
          queryRenderedFeatures: (o: { layers: string[] }) => unknown[];
        };
      }
    ).__map;
    if (!map || !map.getLayer(id)) return { layer: false, rendered: 0 };
    return { layer: true, rendered: map.queryRenderedFeatures({ layers: [id] }).length };
  }, DZ_STATUS_FILL_ID);
}

async function openAt(page: Page) {
  await stubMapCardsBackend(page);
  await openMap(page, "/?z=8&c=-3.2,55.95");
  await waitForMap(page);
  await openLayers(page);
}

test.describe("DZ-HEATMAP PR-B map", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("B-01 200: off by default, then fill and exact key", async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    const hits = await routeDzStatus(page, "ok");
    await openAt(page);
    const toggle = page.getByTestId("layer-toggle-dz_status");
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await expect(toggle).toHaveText(DZ_STATUS_KEY_TITLE);
    expect(hits.status).toBe(0);
    expect((await fillState(page)).layer).toBe(false);
    await expect(page.getByTestId("dz-status-key")).toHaveCount(0);

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "true");
    await expect
      .poll(async () => (await fillState(page)).rendered, { timeout: 30_000 })
      .toBeGreaterThan(0);
    const key = page.getByTestId("dz-status-key");
    await expect(key).toBeVisible();
    const lines = (await key.innerText())
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    expect(lines).toEqual([
      "Estimate status",
      ...LOCKED_LABELS,
      PROPOSED_CREDIT,
      "Uses 2011 local areas (data zones)",
    ]);
    const swatches = await key
      .locator(".layer-legend-swatch")
      .evaluateAll((els) => els.map((el) => getComputedStyle(el).backgroundColor));
    expect(swatches).toEqual([
      "rgb(0, 34, 78)",
      "rgb(189, 189, 189)",
      "rgb(150, 150, 150)",
      "rgb(115, 115, 115)",
      "rgb(217, 217, 217)",
    ]);
    expect(hits.urls.filter((u) => u.includes("2023"))).toEqual([]);
    expect(hits.urls.filter((u) => u.includes("dz-status")).every((u) => new URL(u).search === "")).toBe(true);

    await toggle.click();
    await expect(key).toHaveCount(0);
    await expect.poll(async () => (await fillState(page)).layer).toBe(false);
    assertConsoleClean(gate);
  });

  for (const mode of ["404", "500", "malformed", "refused"] as const) {
    test(`B-${mode}: route fails → no fill, no key`, async ({ page, gate }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      if (mode === "404" || mode === "500") {
        gate.expectError({ urlPath: ROUTE_PATH, status: Number(mode), count: 1 });
      }
      const hits = await routeDzStatus(page, mode);
      await openAt(page);
      const toggle = page.getByTestId("layer-toggle-dz_status");
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "true");
      await expect.poll(() => hits.status, { timeout: 20_000 }).toBe(1);
      // Give the response time to settle, then assert nothing was drawn.
      await page.waitForTimeout(1500);
      expect(await fillState(page)).toEqual({ layer: false, rendered: 0 });
      await expect(page.getByTestId("dz-status-key")).toHaveCount(0);
      await expect(page.getByText(DZ_STATUS_CREDIT)).toHaveCount(0);
      assertConsoleClean(gate);
    });
  }

  test("B-no-tiles: no dz2011 tileset → no switch, no request", async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    const hits = await routeDzStatus(page, "ok", { dz2011: false });
    await openAt(page);
    await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();
    await expect(page.getByTestId("layer-toggle-dz_status")).toHaveCount(0);
    await expect(page.getByTestId("dz-status-key")).toHaveCount(0);
    expect(hits.status).toBe(0);
    expect((await fillState(page)).layer).toBe(false);
    assertConsoleClean(gate);
  });
});
