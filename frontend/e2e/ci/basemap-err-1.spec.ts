import { CI_TINY_PNG, EMPTY_GLYPH_PBF, ensureLayersGroupOpen, injectEsriBasemapKey, openLayers, registerOpenFreeMapFontStub, stubMapCardsBackend } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

registerOpenFreeMapFontStub();

/**
 * BASEMAP-ERR-1 — a failed style request shows the notice, the Data Zone
 * switch still responds, and the console gate records the failure.
 * A later Aerial style.load hides the notice. The error is asserted, not filtered.
 */

const NOTICE =
  "The background map didn't load. The land layers still work. Try reloading the page.";

const ESRI_STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

type EsriStyle = {
  sprite: string;
  glyphs: string;
  sources: Record<
    string,
    { tiles?: string[]; url?: string; attribution?: string; type?: string }
  >;
};

function loadEsriFixture(): EsriStyle {
  if (!existsSync(FIXTURE_PATH)) {
    throw new Error("fixture missing: esri-imagery-style.json");
  }
  return JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as EsriStyle;
}

async function routeEsriFixture(page: Page, style: EsriStyle) {
  const spriteJson = `${style.sprite}.json`;
  const spritePng = `${style.sprite}.png`;

  await page.route(`${ESRI_STYLE_URL}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(style),
    });
  });
  await page.route(spriteJson, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ image: "root.png", width: 1, height: 1 }),
    });
  });
  await page.route(spritePng, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/basemaps-api.arcgis.com/**/*.pbf**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: EMPTY_GLYPH_PBF,
    });
  });
  await page.route("**/ibasemaps-api.arcgis.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
}

test.describe("BASEMAP-ERR-1", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("failed style shows the notice and a later style hides it", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    // Intentional Positron style 500 → MapLibre AJAXError (same-origin chunk loc).
    gate.expectError({
      text: "Error: AJAXError: Internal Server Error (500): https://tiles.openfreemap.org/styles/positron https://tiles.openfreemap.org/styles/positron",
      count: 1,
    });

    await page.route("**/tiles.openfreemap.org/styles/positron**", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "style failed" }),
      });
    });
    await injectEsriBasemapKey(page);
    await routeEsriFixture(page, loadEsriFixture());
    await stubMapCardsBackend(page);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });

    const notice = page.getByTestId("basemap-notice");
    await expect(notice).toBeVisible({ timeout: 20_000 });
    await expect(notice).toContainText(NOTICE);
    await expect(notice.getByRole("button", { name: "Reload" })).toBeVisible();

    await openLayers(page);
    await ensureLayersGroupOpen(page, "places");
    const zones = page.getByTestId("layer-toggle-data_zones");
    await expect(zones).toBeVisible();
    await zones.click();
    await expect(zones).toHaveAttribute("aria-checked", "true");

    expect(
      gate.errors.some((rec) =>
        /positron|openfreemap|AJAXError|Failed to fetch|style failed|500/i.test(
          rec.text,
        ),
      ),
      `expected the style failure in the console:\n${gate.errors.map((e) => e.text).join("\n")}`,
    ).toBe(true);

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("layers-panel")).toBeHidden();
    const toggle = page.getByTestId("basemap-switcher");
    await expect(toggle).toBeVisible();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(notice).toBeHidden({ timeout: 20_000 });
  });
});
