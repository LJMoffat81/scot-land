/**
 * UX-BATCH-2026-11-20 (frozen by Project Lead, 20 Nov 2026).
 *   S1  SITE-CLICK-FALLTHROUGH-1   HLS / LDP site card, no place lookup
 *   F1  CARD-FOOTER-OVERLAP-1      mobile place-card footer vs rows / pill
 *   B1  STORY-MOBILE-FOOTER-CLIP-1 full-width solid bar behind Share / Close
 *   H1  SEARCH-HINT-CLIP-1         hint fits the search input at 390
 *   N1  NAV-TAP-44-1               header links >= 44px at 768 and 1440
 * Synthetic fixtures only. Auto-discovered under e2e/ci/; strict console gate
 * via ./_fixtures. The pound glyph is written as \u00a3 (P7 scans the diff).
 */
import type { Page } from "@playwright/test";
import { expect, test, routeManifestOverride } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  boxesOverlap,
  openPlaceViaCoords,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
  type Box,
} from "./_mapCardsHelpers";
import { PLACE_CARD_EXPERIMENTAL_FOOTER } from "../../lib/placeCard";

registerOpenFreeMapFontStub();

// ---------------------------------------------------------------- S1 ----

const HLS_HEADING = "Housing land supply site";
const LDP_HEADING = "Local Development Plan allocation";
const HLS_LABELS = ["Council", "Housing land audit year", "Site reference"];
const LDP_LABELS = ["Allocated for", "Place", "Plan site code"];
const HLS_NOTE =
  "Sites where councils expect new homes to be built. This shows planning supply, not land value or ownership.";
const HLS_SOURCE = "Improvement Service Spatial Hub · open data";
const LDP_NOTE =
  "Land the Highland Local Development Plan allocates for a specific use. This is a planning designation, not land value or ownership.";
const LDP_SOURCE = "The Highland Council · open data";
const FORBIDDEN =
  /\byet\b|\blater\b|\u00a3|null|undefined|local_auth|hla_year|site_refer|\bsda\b|neighbourhood/i;

const HLS_FULL = {
  local_auth: "  Synthetic Council A ",
  hla_year: "2024/25",
  site_refer: "SYN-HLS-001",
};
const HLS_NO_COUNCIL = { hla_year: "2023/24", site_refer: "SYN-HLS-002" };
const LDP_FULL = { allocation: "Housing", sda: "Synthtown", code: "SY01" };
const LDP_BLANK_CODE = { allocation: "Greenspace", sda: "Synthtown", code: " " };

const SITE_VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
] as const;

function tileset(id: string) {
  return {
    layer: id,
    version: "2026-10-06.abcdef12",
    minzoom: 0,
    maxzoom: 14,
    geometry: "polygon",
    source_layer: id,
    measure: null,
    attribution: `SYNTH ${id} CREDIT`,
    vintage: `SYNTH ${id} VINTAGE`,
    style: {
      fill: { "fill-color": "#6a7f2a", "fill-opacity": 0.3 },
      line: { "line-color": "#6a7f2a", "line-width": 1.2, "line-opacity": 0.9 },
    },
    legend: [{ label: `SYNTH ${id}`, color: "#6a7f2a" }],
  };
}

type Hits = {
  hls?: Record<string, unknown> | null;
  ldp?: Record<string, unknown> | null;
};

/** Manifest with both planning tilesets; tiles are empty (204). */
async function serveSiteManifest(page: Page) {
  await routeManifestOverride(page, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        tilesets: {
          "hls-open": tileset("hls-open"),
          "ldp-highland": tileset("ldp-highland"),
        },
      }),
    });
  });
  await page.route("**/backend/v1/tiles/**/*.mvt", (route) =>
    route.fulfill({ status: 204, body: "" }),
  );
}

/** Record place-lookup calls (Data Zone at-point + platform/place). */
function recordPlaceLookups(page: Page): string[] {
  const seen: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (/\/layers\/context\/data-zones\/at\b|\/platform\/place\b/.test(url)) {
      seen.push(url);
    }
  });
  return seen;
}

async function openSiteMap(page: Page, layers: string) {
  await page.goto(`/?layers=${layers}&z=12&c=-4.2247,57.4778`);
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await waitForMap(page);
}

async function expectLayerVisible(page: Page, id: string, visible: boolean) {
  await expect
    .poll(
      async () =>
        page.evaluate((layerId) => {
          const map = (
            window as unknown as {
              __map?: {
                getLayer(id: string): unknown;
                getLayoutProperty(id: string, p: string): unknown;
              };
            }
          ).__map;
          if (!map?.getLayer(layerId)) return "absent";
          return String(map.getLayoutProperty(layerId, "visibility") ?? "visible");
        }, id),
      { timeout: 30_000 },
    )
    .toMatch(visible ? /^visible$/ : /^(none|absent)$/);
}

/**
 * Stubbed hit: the map answers queryRenderedFeatures for the two site fill
 * layers with the synthetic properties; every other layer is untouched.
 */
async function stubSiteHits(page: Page, hits: Hits) {
  await page.evaluate((h) => {
    const map = (
      window as unknown as {
        __map: {
          queryRenderedFeatures: (...args: unknown[]) => unknown[];
        };
      }
    ).__map;
    const original = map.queryRenderedFeatures.bind(map);
    map.queryRenderedFeatures = (...args: unknown[]) => {
      const opts = args[1] as { layers?: string[] } | undefined;
      const layers = opts?.layers ?? [];
      if (layers.length === 1 && layers[0] === "tile-hls-open-fill") {
        return h.hls ? [{ properties: h.hls }] : [];
      }
      if (layers.length === 1 && layers[0] === "tile-ldp-highland-fill") {
        return h.ldp ? [{ properties: h.ldp }] : [];
      }
      return original(...args);
    };
  }, hits);
}

async function clickMap(page: Page) {
  const canvas = page.locator(".maplibregl-canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas box missing");
  const x = box.width >= 900 ? box.width * 0.7 : box.width / 2;
  const y = box.width >= 900 ? box.height * 0.5 : Math.min(box.height * 0.35, 320);
  await canvas.click({ position: { x, y } });
}

async function siteCardText(page: Page): Promise<string> {
  return (await page.getByTestId("site-card").innerText()).replace(/\s+/g, " ");
}

for (const vp of SITE_VIEWPORTS) {
  test.describe(`S1 site card ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("S1-a HLS + LDP hit: one card, HLS first, exact labels, no place lookup", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await serveSiteManifest(page);
      await openSiteMap(page, "hls-open,ldp-highland");
      await expectLayerVisible(page, "tile-hls-open-fill", true);
      await expectLayerVisible(page, "tile-ldp-highland-fill", true);
      await stubSiteHits(page, { hls: HLS_FULL, ldp: LDP_FULL });
      const lookups = recordPlaceLookups(page);
      await clickMap(page);

      const card = page.getByTestId("site-card");
      await expect(card).toBeVisible({ timeout: 15_000 });
      const sections = card.locator("section");
      await expect(sections).toHaveCount(2);
      await expect(sections.nth(0)).toHaveAttribute("data-testid", "site-card-hls");
      await expect(sections.nth(1)).toHaveAttribute("data-testid", "site-card-ldp");
      const hlsHeading = page.getByTestId("site-card-hls-heading");
      const ldpHeading = page.getByTestId("site-card-ldp-heading");
      await expect(hlsHeading).toHaveText(HLS_HEADING);
      await expect(ldpHeading).toHaveText(LDP_HEADING);
      await expect(hlsHeading).toHaveJSProperty("tagName", "H2");
      await expect(ldpHeading).toHaveJSProperty("tagName", "H2");
      const hls = page.getByTestId("site-card-hls");
      const ldp = page.getByTestId("site-card-ldp");
      await expect(hls.locator("dt")).toHaveText(HLS_LABELS);
      await expect(hls.locator("dd")).toHaveText([
        "Synthetic Council A",
        "2024/25",
        "SYN-HLS-001",
      ]);
      await expect(ldp.locator("dt")).toHaveText(LDP_LABELS);
      await expect(ldp.locator("dd")).toHaveText(["Housing", "Synthtown", "SY01"]);
      await expect(page.getByTestId("site-card-hls-note")).toHaveText(HLS_NOTE);
      await expect(page.getByTestId("site-card-hls-source")).toHaveText(HLS_SOURCE);
      await expect(page.getByTestId("site-card-ldp-note")).toHaveText(LDP_NOTE);
      await expect(page.getByTestId("site-card-ldp-source")).toHaveText(LDP_SOURCE);
      // PL ruling 2026-11-20: the site card carries no disclaimer footer.
      await expect(card.getByTestId("site-card-footer")).toHaveCount(0);
      await expect(card.getByTestId("place-card-footer")).toHaveCount(0);
      await expect(card.locator(".place-card-experimental-footer")).toHaveCount(0);
      await expect(card).not.toContainText(PLACE_CARD_EXPERIMENTAL_FOOTER);
      await expect(card).not.toContainText("Experimental estimate");
      await expect(page.getByTestId("place-card")).toHaveCount(0);

      const close = page.getByTestId("site-card-close");
      await expect(close).toHaveText("Close");
      await expect(close).toHaveAttribute("aria-label", "Close site card");
      const closeBox = await close.boundingBox();
      expect(closeBox, "S1 close box").toBeTruthy();
      expect(closeBox!.width).toBeGreaterThanOrEqual(44);
      expect(closeBox!.height).toBeGreaterThanOrEqual(44);

      expect(await siteCardText(page)).not.toMatch(FORBIDDEN);
      // Settle well past the 150ms identify debounce: no place lookup at all.
      await page.waitForTimeout(1_000);
      expect(lookups, "S1 place lookup fired on a site hit").toEqual([]);

      await close.click();
      await expect(page.getByTestId("site-card")).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("S1-b LDP code ' ' renders no Plan site code row", async ({ page, gate }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await serveSiteManifest(page);
      await openSiteMap(page, "ldp-highland");
      await expectLayerVisible(page, "tile-ldp-highland-fill", true);
      await stubSiteHits(page, { ldp: LDP_BLANK_CODE });
      await clickMap(page);
      const ldp = page.getByTestId("site-card-ldp");
      await expect(ldp).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("site-card-hls")).toHaveCount(0);
      await expect(ldp.locator("dt")).toHaveText(["Allocated for", "Place"]);
      await expect(ldp.locator("dd")).toHaveText(["Greenspace", "Synthtown"]);
      await expect(ldp.getByText("Plan site code")).toHaveCount(0);
      expect(await siteCardText(page)).not.toMatch(FORBIDDEN);
      assertConsoleClean(gate);
    });

    test("S1-c HLS local_auth missing renders no Council row", async ({ page, gate }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await serveSiteManifest(page);
      await openSiteMap(page, "hls-open");
      await expectLayerVisible(page, "tile-hls-open-fill", true);
      await stubSiteHits(page, { hls: HLS_NO_COUNCIL });
      await clickMap(page);
      const hls = page.getByTestId("site-card-hls");
      await expect(hls).toBeVisible({ timeout: 15_000 });
      await expect(page.getByTestId("site-card-ldp")).toHaveCount(0);
      await expect(hls.locator("dt")).toHaveText([
        "Housing land audit year",
        "Site reference",
      ]);
      await expect(hls.getByText("Council", { exact: true })).toHaveCount(0);
      expect(await siteCardText(page)).not.toMatch(FORBIDDEN);
      assertConsoleClean(gate);
    });

    test("S1-d site layers off: no site card, place lookup still runs", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await serveSiteManifest(page);
      await openSiteMap(page, "data_zones");
      await expectLayerVisible(page, "tile-hls-open-fill", false);
      await expectLayerVisible(page, "tile-ldp-highland-fill", false);
      // A hit is stubbed, but the layers are hidden: it must be ignored.
      await stubSiteHits(page, { hls: HLS_FULL, ldp: LDP_FULL });
      const lookups = recordPlaceLookups(page);
      await clickMap(page);
      await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
      await expect(page.getByTestId("site-card")).toHaveCount(0);
      await expect.poll(() => lookups.length, { timeout: 15_000 }).toBeGreaterThan(0);
      assertConsoleClean(gate);
    });
  });
}

// ---------------------------------------------------------------- F1 ----

for (const vp of [
  { width: 390, height: 844 },
  { width: 360, height: 740 },
] as const) {
  test.describe(`F1 place-card footer ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("F1 footer sits on the sheet edge; rows and pill scroll clear of it", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      const card = await openPlaceViaCoords(page);
      await expect(card.getByTestId("place-card-figure-status")).toBeAttached({
        timeout: 30_000,
      });
      await expect(page.locator(".map-panel-slot--place")).toHaveClass(
        /map-panel-slot--half/,
      );
      const scroll = page.getByTestId("map-panel-scroll");
      const footer = card.getByTestId("place-card-footer");
      await scroll.evaluate((el) => {
        el.scrollTop = 0;
      });
      const box = async (l: ReturnType<Page["locator"]>, label: string) => {
        const b = await l.boundingBox();
        if (!b) throw new Error(`${label}: no box`);
        return b as Box;
      };
      const port = await scroll.evaluate((el) => {
        const r = el.getBoundingClientRect();
        return { top: r.top, bottom: r.top + el.clientHeight };
      });
      // F1-a: no strip of card text painted under the sticky footer.
      const foot0 = await box(footer, "footer");
      expect(
        Math.abs(foot0.y + foot0.height - port.bottom),
        "F1-a footer bottom on the sheet edge",
      ).toBeLessThanOrEqual(1);

      // F1-b: scrolled into view, the label and the pill stay clear of it.
      for (const id of ["place-card-agr-label", "place-card-figure-status"]) {
        const target = card.getByTestId(id);
        await target.evaluate((el) =>
          el.scrollIntoView({ block: "end", behavior: "instant" }),
        );
        await page.waitForTimeout(100);
        const t = await box(target, id);
        const f = await box(footer, "footer");
        expect(boxesOverlap(t, f), `F1-b ${id} intersects the footer`).toBe(false);
        expect(t.y, `F1-b ${id} reachable (top)`).toBeGreaterThanOrEqual(port.top - 1);
        expect(t.y + t.height, `F1-b ${id} reachable (bottom)`).toBeLessThanOrEqual(
          f.y + 1,
        );
      }
      assertConsoleClean(gate);
    });
  });
}

// ---------------------------------------------------------------- B1 ----

/** Count non-white pixels in a clip, skipping the given rects (page px). */
async function inkPixels(page: Page, clip: Box, skip: Box[]): Promise<number> {
  const png = await page.screenshot({ clip });
  return page.evaluate(
    async ({ b64, clip: c, skip: s }) => {
      const img = new Image();
      img.src = `data:image/png;base64,${b64}`;
      await img.decode();
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth;
      cv.height = img.naturalHeight;
      const ctx = cv.getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.drawImage(img, 0, 0);
      const scale = img.naturalWidth / c.width;
      const data = ctx.getImageData(0, 0, cv.width, cv.height).data;
      let ink = 0;
      for (let y = 0; y < cv.height; y += 1) {
        for (let x = 0; x < cv.width; x += 1) {
          const px = c.x + x / scale;
          const py = c.y + y / scale;
          const skipped = s.some(
            (r) => px >= r.x && px <= r.x + r.width && py >= r.y && py <= r.y + r.height,
          );
          if (skipped) continue;
          const i = (y * cv.width + x) * 4;
          if (data[i] < 235 || data[i + 1] < 235 || data[i + 2] < 235) ink += 1;
        }
      }
      return ink;
    },
    { b64: png.toString("base64"), clip, skip },
  );
}

test.describe("B1 story footer bar 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("B1 Share / Close sit on a full-width solid bar mid-scroll", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await page.goto("/");
    await waitForMap(page);
    if ((await page.getByTestId("layers-panel").count()) === 0) {
      await page.getByTestId("hud-layers-btn").click();
    }
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    for (const viewId of ["idle-land", "who-holds-scotland"] as const) {
      await page.getByTestId(`map-view-${viewId}`).click();
      await expect(page.getByTestId("map-view-detail")).toBeVisible();
      await expect(page.locator(".map-view-detail tbody tr")).toHaveCount(32);
      const scroll = page.getByTestId("map-panel-scroll");
      // Mid-scroll: table rows run behind the stuck buttons.
      await page
        .locator(".map-view-detail tbody tr:nth-child(12)")
        .evaluate((el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
      await page.waitForTimeout(150);
      const share = await page.getByTestId("map-view-share").boundingBox();
      const close = await page.getByTestId("map-view-close").boundingBox();
      const port = await scroll.evaluate((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.left, y: r.top, width: el.clientWidth, bottom: r.top + el.clientHeight };
      });
      expect(share && close, "B1 buttons").toBeTruthy();
      const pad = 3;
      const skip = [share!, close!].map((b) => ({
        x: b.x - pad,
        y: b.y - pad,
        width: b.width + 2 * pad,
        height: b.height + 2 * pad,
      }));
      // Band: from the buttons' top to the sheet's bottom edge, full width.
      const top = Math.min(share!.y, close!.y);
      const clip = {
        x: port.x + 1,
        y: top,
        width: port.width - 2,
        height: port.bottom - top - 1,
      };
      expect(clip.height, `B1 ${viewId} band height`).toBeGreaterThan(44);
      expect(await inkPixels(page, clip, skip), `B1 ${viewId} text shows through`).toBe(0);
      await page.getByTestId("map-view-close").click();
      await expect(page.getByTestId("map-view-detail")).toHaveCount(0);
    }
    assertConsoleClean(gate);
  });
});

// ---------------------------------------------------------------- H1 ----

test.describe("H1 search hint 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("H1 the whole hint fits inside the input, clear of Search", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await page.goto("/");
    await waitForMap(page);
    const fit = await page.evaluate(() => {
      const input = document.getElementById("place-query");
      const go = document.querySelector(".hud-search-go");
      if (!(input instanceof HTMLInputElement) || !(go instanceof HTMLElement)) {
        throw new Error("search parts missing");
      }
      const cs = getComputedStyle(input);
      const ph = getComputedStyle(input, "::placeholder");
      const ctx = document.createElement("canvas").getContext("2d");
      if (!ctx) throw new Error("no 2d context");
      ctx.font = `${ph.fontStyle} ${ph.fontWeight} ${ph.fontSize} ${ph.fontFamily}`;
      return {
        hint: ctx.measureText(input.placeholder).width,
        usable:
          input.clientWidth -
          Number.parseFloat(cs.paddingLeft) -
          Number.parseFloat(cs.paddingRight),
        inputRight: input.getBoundingClientRect().right,
        goLeft: go.getBoundingClientRect().left,
        placeholder: input.placeholder,
      };
    });
    expect(fit.placeholder).toBe("Search a postcode, or tap the map");
    expect(fit.hint, "H1 hint wider than the usable input").toBeLessThanOrEqual(
      fit.usable,
    );
    expect(fit.inputRight, "H1 input runs under Search").toBeLessThanOrEqual(
      fit.goLeft + 0.5,
    );
    assertConsoleClean(gate);
  });
});

// ---------------------------------------------------------------- N1 ----

for (const vp of [
  { width: 768, height: 1024 },
  { width: 1440, height: 900 },
] as const) {
  test.describe(`N1 nav links ${vp.width}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("N1 every visible site-nav link is at least 44px tall", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      for (const path of ["/", "/about"]) {
        await page.goto(path);
        const links = page.locator(".site-nav-links a");
        await expect(links.first()).toBeVisible({ timeout: 30_000 });
        const heights = await links.evaluateAll((els) =>
          els
            .filter((el) => el.getClientRects().length > 0)
            .map((el) => [el.textContent ?? "", el.getBoundingClientRect().height] as const),
        );
        expect(heights.length, `N1 ${path} links`).toBeGreaterThanOrEqual(3);
        for (const [name, h] of heights) {
          expect(h, `N1 ${path} "${name}"`).toBeGreaterThanOrEqual(44);
        }
      }
      assertConsoleClean(gate);
    });
  });
}

// ---------------------------------------------------------------- S2 ----
// UX-BATCH-2026-11-20 r2 (VD FAIL on #323): after a site tap the camera
// recentres on the pin, so the half sheet and the search bar never hide it.

/** Resolve once the map has no camera move pending and has rendered idle. */
async function waitForCameraSettled(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        const map = (
          window as unknown as {
            __map: {
              isMoving(): boolean;
              once(type: string, fn: () => void): void;
              triggerRepaint(): void;
            };
          }
        ).__map;
        if (!map.isMoving()) {
          // Nothing in flight: one repaint gives a fresh idle to wait on.
          map.once("idle", () => resolve());
          map.triggerRepaint();
          return;
        }
        map.once("moveend", () => map.once("idle", () => resolve()));
      }),
  );
}

for (const tap of [
  { x: 195, y: 200 },
  { x: 195, y: 650 },
] as const) {
  test.describe(`S2 site pin 390x844 tap ${tap.x},${tap.y}`, () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("S2 pin fully visible between the search bar and the sheet top", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await serveSiteManifest(page);
      await openSiteMap(page, "hls-open,ldp-highland");
      await expectLayerVisible(page, "tile-hls-open-fill", true);
      await expectLayerVisible(page, "tile-ldp-highland-fill", true);
      await stubSiteHits(page, { hls: HLS_FULL, ldp: LDP_FULL });
      await page
        .locator(".maplibregl-canvas")
        .click({ position: { x: tap.x, y: tap.y } });

      await expect(page.getByTestId("site-card")).toBeVisible({ timeout: 15_000 });
      const pin = page.getByRole("img", { name: "Selected place" });
      await expect(pin).toHaveCount(1);
      await waitForCameraSettled(page);

      const search = page.locator(".hud-search").first();
      const sheet = page.locator(".map-panel-slot--place").first();
      await expect
        .poll(
          async () => {
            const [p, s, h] = await Promise.all([
              pin.boundingBox(),
              search.boundingBox(),
              sheet.boundingBox(),
            ]);
            if (!p || !s || !h) return "missing box";
            const issues: string[] = [];
            if (p.y < s.y + s.height) {
              issues.push(`pin top ${p.y} above search bottom ${s.y + s.height}`);
            }
            if (p.y + p.height > h.y) {
              issues.push(`pin bottom ${p.y + p.height} below sheet top ${h.y}`);
            }
            return issues.join("; ") || "ok";
          },
          { timeout: 10_000, message: `S2 pin after tap ${tap.x},${tap.y}` },
        )
        .toBe("ok");
      assertConsoleClean(gate);
    });
  });
}
