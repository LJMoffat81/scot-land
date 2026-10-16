import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * UI-TWEAKS-1 T1 — Layers panel height and position.
 * 1280×800: top aligns with Layers button (±2 px); fills down to bottom
 * inset / attribution; one inner scroller; no overlap with legend or card.
 * 390×844: sheet pattern (redesign half detent) without covering the card.
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
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
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
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: null, name: null, vintage: null }),
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
      body: JSON.stringify({ layers: [] }),
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
  await expect(page.locator("aside.hud-tools")).toBeVisible();
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
    const shell = document.querySelector("aside.hud-tools") as HTMLElement | null;
    const scroller = shell?.querySelector(".layer-panel") as HTMLElement | null;
    if (!shell || !scroller) {
      return { ok: false as const, reason: "missing shell or scroller" };
    }
    const probe = document.createElement("div");
    probe.dataset.testid = "layers-overflow-probe";
    probe.style.height = "2400px";
    probe.setAttribute("aria-hidden", "true");
    scroller.appendChild(probe);

    const shellOy = getComputedStyle(shell).overflowY;
    const scrollerOy = getComputedStyle(scroller).overflowY;
    const before = scroller.scrollTop;
    scroller.scrollTop = 400;
    const after = scroller.scrollTop;
    const bodyScrolled = document.documentElement.scrollTop + document.body.scrollTop;
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
  expect(scrollState.scrollHeight, "inner content taller than panel").toBeGreaterThan(
    scrollState.clientHeight + 1,
  );
  expect(scrollState.scrolled, "inner list scrolls").toBe(true);
  expect(scrollState.bodyScrolled, "page must not scroll").toBe(0);
  expect(scrollState.mapScrolled, "map must not scroll").toBe(0);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`UI-TWEAKS-1 Layers panel (${viewport.width}×${viewport.height})`, () => {
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
        return true;
      });
      expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
    });

    test("height, position, scroll, no cover legend/card", async ({ page }) => {
      test.setTimeout(120_000);
      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor();
      await page.locator("#place-query").waitFor();

      const layersBtn = await openLayers(page);
      const drawer = page.locator("aside.hud-tools");
      const btnBox = await boxOf(layersBtn, "Layers button");
      const drawerBox = await boxOf(drawer, "Layers drawer");

      if (viewport.width >= 900) {
        // Desktop: top edge lines up with Layers button (±2 px).
        await expect(async () => {
          const d = await drawer.boundingBox();
          const b = await layersBtn.boundingBox();
          expect(d, "drawer box").toBeTruthy();
          expect(b, "btn box").toBeTruthy();
          expect(
            Math.abs(d!.y - b!.y),
            `top delta ${d!.y} vs btn ${b!.y}`,
          ).toBeLessThanOrEqual(2);
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
        // panel bottom ≥ viewport − (bottom inset + attribution[/footer])
        const bottomAllowance = footerBox.height + attribH;
        expect(
          freshDrawer.y + freshDrawer.height,
          "panel reaches bottom inset / attribution",
        ).toBeGreaterThanOrEqual(viewport.height - bottomAllowance - 2);
      } else {
        // Mobile sheet: bottom-anchored; fills the sheet height; not under the button.
        expect(drawerBox.y, "sheet below Layers button").toBeGreaterThan(btnBox.y);
        const footer = page.getByTestId("map-stamp-footer");
        const footerBox = await boxOf(footer, "map footer");
        expect(
          drawerBox.y + drawerBox.height,
          "sheet reaches above footer",
        ).toBeGreaterThanOrEqual(viewport.height - footerBox.height - 4);
        expect(drawerBox.height, "sheet ~55dvh").toBeGreaterThan(viewport.height * 0.45);
      }

      await assertInnerListScrolls(page);

      // Legend must stay clear of the drawer.
      const legendPill = page.getByRole("button", { name: "Show legend" });
      const legendPanel = page.getByTestId("map-legend-panel");
      if ((await legendPill.count()) > 0 && (await legendPill.isVisible())) {
        assertPairClear(
          drawerBox,
          await boxOf(legendPill, "legend pill"),
          "Layers vs legend pill",
        );
      } else if (await legendPanel.isVisible()) {
        assertPairClear(
          drawerBox,
          await boxOf(legendPanel, "legend panel"),
          "Layers vs legend",
        );
      }

      // Place card + Layers: no bbox intersection (desktop side-by-side; mobile sheet).
      // Layers button stays above the drawer (hud-top z-index) so this click works.
      await page.getByTestId("hud-layers-btn").click();
      await expect(page.getByTestId("layers-panel")).toBeHidden();
      const card = await openPlaceCard(page);
      await openLayers(page);
      const drawerOpen = page.locator("aside.hud-tools");
      await expect(async () => {
        assertPairClear(
          await boxOf(drawerOpen, "Layers drawer with card"),
          await boxOf(card, "place card"),
          "Layers vs place card",
        );
      }).toPass({ timeout: 10_000 });
      // Card remains clickable (close control present and enabled).
      const close = page.getByRole("button", { name: "Close place card" });
      await expect(close).toBeVisible();
      await expect(close).toBeEnabled();
    });
  });
}
