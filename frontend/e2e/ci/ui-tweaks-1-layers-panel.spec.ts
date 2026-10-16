import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * UI-TWEAKS-1 T1 — Layers panel height and position (MAP-CARDS one-panel slot).
 * 1280×800: left column clears the HUD (brand side); fills down to bottom
 * inset / attribution; one inner scroller; XOR with place (no dual float).
 * 390×844: sheet pattern (full detent) without covering stamp footer.
 */

const consoleErrors: string[] = [];

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

type Box = { x: number; y: number; width: number; height: number };

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function stubBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_STUB),
      });
      return;
    }
    if (/\/place(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
      return;
    }
    if (/\/layers\/context\/data-zones\/at/i.test(url)) {
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
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
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

async function boxOf(locator: Locator, label: string): Promise<Box> {
  await expect(locator, label).toBeVisible();
  let box: Box | null = null;
  await expect(async () => {
    box = await locator.boundingBox();
    expect(box, `${label} bounding box`).toBeTruthy();
    expect(box!.width, `${label} width`).toBeGreaterThan(0);
    expect(box!.height, `${label} height`).toBeGreaterThan(0);
  }).toPass({ timeout: 15_000 });
  return box!;
}

function assertPairClear(a: Box, b: Box, label: string) {
  expect(
    boxesOverlap(a, b),
    `${label} must not intersect: a=${JSON.stringify(a)} b=${JSON.stringify(b)}`,
  ).toBe(false);
}

async function openLayers(page: Page) {
  const layersBtn = page.getByTestId("hud-layers-btn");
  await layersBtn.click();
  await expect(page.getByTestId("layers-panel")).toBeVisible();
  await expect(page.getByTestId("map-panel-slot")).toBeVisible();
  await expect(page.getByTestId("map-panel-slot")).toHaveAttribute(
    "data-panel",
    "layers",
  );
  return layersBtn;
}

async function openPlaceCard(page: Page) {
  await page.locator("#place-query").fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
}

async function assertInnerListScrolls(page: Page) {
  const scrollState = await page.evaluate(() => {
    const shell = document.querySelector(
      '[data-testid="map-panel-slot"]',
    ) as HTMLElement | null;
    const scroller = shell?.querySelector(
      '[data-testid="map-panel-scroll"]',
    ) as HTMLElement | null;
    if (!shell || !scroller) {
      return { ok: false as const, reason: "missing shell or scroller" };
    }
    const probe = document.createElement("div");
    probe.dataset.testid = "layers-overflow-probe";
    probe.style.cssText =
      "height:2400px;min-height:2400px;flex-shrink:0;display:block;";
    probe.setAttribute("aria-hidden", "true");
    const mount =
      (scroller.querySelector(
        ".map-panel-slot-focus",
      ) as HTMLElement | null) ?? scroller;
    mount.appendChild(probe);

    const shellOy = getComputedStyle(shell).overflowY;
    const scrollerOy = getComputedStyle(scroller).overflowY;
    const before = scroller.scrollTop;
    scroller.scrollTop = 400;
    const after = scroller.scrollTop;
    const bodyScrolled =
      document.documentElement.scrollTop + document.body.scrollTop;
    const mapWrap = document.querySelector(".map-wrap") as HTMLElement | null;
    const mapScrolled = mapWrap ? mapWrap.scrollTop : 0;

    probe.remove();

    return {
      ok: true as const,
      shellOy,
      scrollerOy,
      scrollHeight: scroller.scrollHeight,
      clientHeight: scroller.clientHeight,
      scrolled: after > before,
      bodyScrolled,
      mapScrolled,
      shellScrollHeight: shell.scrollHeight,
      shellClientHeight: shell.clientHeight,
    };
  });

  expect(scrollState.ok, "scroll probe").toBe(true);
  if (!scrollState.ok) return;
  expect(
    scrollState.scrollerOy === "auto" || scrollState.scrollerOy === "scroll",
    `inner scroller overflow-y=${scrollState.scrollerOy}`,
  ).toBe(true);
  expect(
    scrollState.shellOy === "hidden" || scrollState.shellOy === "clip",
    `shell overflow-y=${scrollState.shellOy}`,
  ).toBe(true);
  expect(
    scrollState.scrollHeight,
    "inner content taller than panel",
  ).toBeGreaterThan(scrollState.clientHeight + 1);
  expect(scrollState.scrolled, "inner list scrolls").toBe(true);
  expect(scrollState.bodyScrolled, "page must not scroll").toBe(0);
  expect(scrollState.mapScrolled, "map must not scroll").toBe(0);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(
    `UI-TWEAKS-1 Layers panel (${viewport.width}×${viewport.height})`,
    () => {
      test.use({ viewport });

      test.beforeEach(async ({ page }) => {
        consoleErrors.length = 0;
        page.on("console", (msg) => {
          if (msg.type() === "error") consoleErrors.push(msg.text());
        });
        page.on("pageerror", (err) => {
          consoleErrors.push(String(err));
        });
        await stubBackend(page);
      });

      test.afterEach(async () => {
        const meaningful = consoleErrors.filter((line) => {
          if (/favicon/i.test(line)) return false;
          if (/Download the React DevTools/i.test(line)) return false;
          if (/Failed to load resource:.*(?:404|503)/i.test(line)) return false;
          if (/AbortError|aborted|Failed to fetch|net::ERR_/i.test(line)) {
            return false;
          }
          return true;
        });
        expect(
          meaningful,
          `console errors:\n${meaningful.join("\n")}`,
        ).toEqual([]);
      });

      test("height, position, scroll, no cover legend/card", async ({
        page,
      }) => {
        test.setTimeout(120_000);
        await page.goto("/");
        await page.locator(".maplibregl-canvas").waitFor();
        await page.locator("#place-query").waitFor();

        // Measure Layers button before open — at mobile full detent the
        // button is intentionally hidden under the sheet.
        const layersBtn = page.getByTestId("hud-layers-btn");
        const btnBox = await boxOf(layersBtn, "Layers button");
        await openLayers(page);
        const drawer = page.getByTestId("map-panel-slot");
        const drawerBox = await boxOf(drawer, "Layers drawer");

        if (viewport.width >= 900) {
          // Desktop left column: clear the HUD (below Layers button), not
          // flush with it — brand mark shares the left edge.
          await expect(async () => {
            const d = await drawer.boundingBox();
            const b = await layersBtn.boundingBox();
            expect(d, "drawer box").toBeTruthy();
            expect(b, "btn box").toBeTruthy();
            expect(
              d!.y,
              `panel top ${d!.y} must clear Layers btn bottom ${b!.y + b!.height}`,
            ).toBeGreaterThanOrEqual(b!.y + b!.height - 2);
          }).toPass({ timeout: 10_000 });

          const freshDrawer = await boxOf(drawer, "Layers drawer aligned");
          const footer = page.getByTestId("map-stamp-footer");
          const footerBox = await boxOf(footer, "map footer");
          const attrib = page.locator(".maplibregl-ctrl-attrib");
          let attribH = 28;
          if ((await attrib.count()) > 0 && (await attrib.first().isVisible())) {
            const a = await attrib.first().boundingBox();
            if (a) attribH = Math.max(attribH, a.height);
          }
          const bottomAllowance = footerBox.height + attribH;
          expect(
            freshDrawer.y + freshDrawer.height,
            "panel reaches bottom inset / attribution",
          ).toBeGreaterThanOrEqual(viewport.height - bottomAllowance - 2);
        } else {
          // Mobile full sheet: bottom-anchored; fills most of the viewport.
          expect(drawerBox.y, "sheet below Layers button rest y").toBeGreaterThan(
            btnBox.y - 8,
          );
          const footer = page.getByTestId("map-stamp-footer");
          const footerBox = await boxOf(footer, "map footer");
          expect(
            drawerBox.y + drawerBox.height,
            "sheet reaches above footer",
          ).toBeGreaterThanOrEqual(viewport.height - footerBox.height - 4);
          expect(
            drawerBox.height,
            "sheet ~full detent",
          ).toBeGreaterThan(viewport.height * 0.45);
        }

        await assertInnerListScrolls(page);

        // Legend strip / attribution stay clear of the drawer when present.
        const legendStrip = page.getByTestId("legend-strip");
        if (
          (await legendStrip.count()) > 0 &&
          (await legendStrip.isVisible())
        ) {
          assertPairClear(
            drawerBox,
            await boxOf(legendStrip, "legend strip"),
            "Layers vs legend strip",
          );
        }
        const attribLine = page.getByTestId("map-attribution-line");
        if (
          (await attribLine.count()) > 0 &&
          (await attribLine.isVisible())
        ) {
          assertPairClear(
            drawerBox,
            await boxOf(attribLine, "attribution line"),
            "Layers vs attribution",
          );
        }

        // MAP-CARDS XOR: place card is aside while Layers occupies the slot.
        // Prefer slot × — Layers button is hidden at mobile full detent.
        await page.getByTestId("map-panel-slot-close").click();
        await expect(page.getByTestId("layers-panel")).toBeHidden();
        const card = await openPlaceCard(page);
        await expect(card).toBeVisible();
        await openLayers(page);
        await expect(page.getByTestId("place-card")).toHaveCount(0);
        await expect(page.getByTestId("layers-panel")).toBeVisible();
        // Close Layers → place card restored.
        await page.getByTestId("map-panel-slot-close").click();
        await expect(page.getByTestId("place-card")).toBeVisible({
          timeout: 15_000,
        });
        const close = page.getByRole("button", { name: "Close place card" });
        await expect(close).toBeVisible();
        await expect(close).toBeEnabled();
      });
    },
  );
}
