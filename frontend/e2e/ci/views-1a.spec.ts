/**
 * VIEWS-1a — story views on the Layers card and the ?view= contract.
 * Synthetic backend stubs only (stubMapCardsBackend). Auto-discovered.
 */
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import type { Page } from "@playwright/test";
import { MAP_LAYER_REGISTRY } from "../../lib/mapLayerRegistry";
import { MAP_VIEW_PRESETS } from "../../lib/mapViews";

registerOpenFreeMapFontStub();

const ACCESS_FINDING =
  "Travel times to a GP, shops, schools and a post office vary widely between Scotland's local areas.";
const ACCESS_SOURCE = "Scottish Government SIMD, 2020; OS Boundary-Line, 2026";
const ACCESS_GAP =
  "What this doesn't show: land values, or travel times from any single home.";

function viewParams(page: Page): string[] {
  return new URL(page.url()).searchParams.getAll("view");
}

function layerParam(page: Page): string[] {
  return (new URL(page.url()).searchParams.get("layers") ?? "")
    .split(",")
    .filter(Boolean)
    .sort();
}

async function boot(page: Page, path: string) {
  await page.addInitScript(() => {
    const w = window as unknown as { __copied?: string[] };
    w.__copied = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (s: string) => void w.__copied!.push(s) },
    });
  });
  await stubMapCardsBackend(page);
  await openMap(page, path);
  await waitForMap(page);
  await openLayers(page);
}

test.describe("VIEWS-1a", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("V-E1 ?view=access-to-services boots the view with exact copy", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    await boot(page, "/?view=access-to-services");
    await expect(page.getByTestId("map-views-heading")).toHaveText("Views");
    await expect(page.getByTestId("map-views-intro")).toHaveText(
      "Choose a view to see one pattern on the map.",
    );
    await expect(page.getByTestId("layers-all-heading")).toHaveText("All layers");
    await expect(page.locator('[data-testid^="map-view-"][aria-pressed]')).toHaveCount(MAP_VIEW_PRESETS.length);
    await expect(page.getByTestId("map-view-access-to-services")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("map-view-access-to-services")).toHaveText("Access to services");
    await expect(page.getByTestId("map-view-finding")).toHaveText(ACCESS_FINDING);
    await expect(page.getByTestId("map-view-source")).toHaveText(ACCESS_SOURCE);
    await expect(page.getByTestId("map-view-does-not-show")).toHaveText(ACCESS_GAP);
    await expect(page.getByTestId("map-view-key-access_services")).toBeVisible();
    await expect(page.getByTestId("map-view-key-councils")).toBeVisible();
    await expect(page.getByTestId("map-view-close")).toHaveText("Close view");
    const detail = (await page.getByTestId("map-view-detail").innerText()).toLowerCase();
    expect(detail).not.toMatch(/\u00a3|rent|neighbou?rhood|value comes from location/);
    await expect.poll(() => viewParams(page)).toEqual(["access-to-services"]);
    await expect.poll(() => layerParam(page)).toEqual(["access_services", "councils"]);
    assertConsoleClean(gate);
  });

  test("V-E1b Estimate badge absent on every shipped view", async ({ page }) => {
    test.setTimeout(180_000);
    expect(MAP_VIEW_PRESETS.length).toBeGreaterThan(0);
    await boot(page, "/");
    for (const v of MAP_VIEW_PRESETS) {
      await page.getByTestId(`map-view-${v.id}`).click();
      await expect(page.getByTestId("map-view-detail")).toHaveAttribute("data-view", v.id);
      await expect(page.getByTestId("map-view-estimate")).toHaveCount(0);
    }
  });

  test("V-E1c Share this view copies the link, then shows Copied", async ({ page }) => {
    test.setTimeout(180_000);
    await boot(page, "/?view=access-to-services");
    const share = page.getByTestId("map-view-share");
    await expect(share).toHaveText("Share this view");
    await share.click();
    await expect(share).toHaveText("Copied");
    const copied = await page.evaluate(() => (window as unknown as { __copied: string[] }).__copied);
    expect(copied).toEqual([`${new URL(page.url()).origin}/map?view=access-to-services`]);
    await expect(share).toHaveText("Share this view", { timeout: 5_000 });
  });

  for (const path of [
    "/?view=",
    "/?view=%20",
    "/?view=nope",
    "/?view=agr",
    "/?view=shared-wealth",
    "/?view=nope&view=access-to-services",
  ]) {
    test(`V-E2 ${path} falls back to the default map`, async ({ page }) => {
      test.setTimeout(180_000);
      await boot(page, path);
      await expect(page.getByTestId("map-view-access-to-services")).toHaveAttribute("aria-pressed", "false");
      await expect(page.getByTestId("map-view-detail")).toHaveCount(0);
      await expect.poll(() => viewParams(page)).toEqual([]);
      await expect.poll(() => layerParam(page)).toEqual(["data_zones"]);
    });
  }

  test("V-E3 repeated ?view= uses the first value", async ({ page }) => {
    test.setTimeout(180_000);
    await boot(page, "/?view=access-to-services&view=nope");
    await expect(page.getByTestId("map-view-access-to-services")).toHaveAttribute("aria-pressed", "true");
    await expect.poll(() => viewParams(page)).toEqual(["access-to-services"]);
    await expect.poll(() => layerParam(page)).toEqual(["access_services", "councils"]);
  });

  test("V-E4 pick, diverge and close round-trip the URL", async ({ page }) => {
    test.setTimeout(180_000);
    await boot(page, "/");
    await page.getByTestId("map-view-access-to-services").click();
    await expect.poll(() => viewParams(page)).toEqual(["access-to-services"]);
    await expect.poll(() => layerParam(page)).toEqual(["access_services", "councils"]);
    await expect(page.getByTestId("layer-toggle-data_zones")).toHaveAttribute("aria-checked", "false");
    await page.getByTestId("layer-toggle-data_zones").click();
    await expect.poll(() => viewParams(page)).toEqual([]);
    await expect(page.getByTestId("map-view-access-to-services")).toHaveAttribute("aria-pressed", "false");
    await page.getByTestId("map-view-access-to-services").click();
    await expect.poll(() => viewParams(page)).toEqual(["access-to-services"]);
    await page.getByTestId("map-view-close").click();
    await expect.poll(() => viewParams(page)).toEqual([]);
    await expect(page.getByTestId("map-view-detail")).toHaveCount(0);
    await page.reload();
    await waitForMap(page);
    await expect.poll(() => viewParams(page)).toEqual([]);
  });

  test("V-E5 'coming' layers are on the roadmap, not the Layers card", async ({ page }) => {
    test.setTimeout(180_000);
    const coming = MAP_LAYER_REGISTRY.filter((e) => e.coming);
    expect(coming.length).toBeGreaterThan(0);
    await boot(page, "/");
    for (const e of coming) {
      await expect(page.getByTestId(`layer-toggle-${e.id}`)).toHaveCount(0);
    }
    await page.goto("/roadmap");
    const text = await page.getByTestId("roadmap-page").innerText();
    for (const e of coming) expect(text).toContain(e.label);
  });
});
