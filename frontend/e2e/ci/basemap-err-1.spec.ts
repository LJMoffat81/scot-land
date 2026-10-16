import {
  ensureLayersGroupOpen,
  openLayers,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import { expect, test } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * BASEMAP-ERR-1 — a failed style request shows the notice, the Data Zone
 * switch still responds, and the console gate records the failure.
 * A later style.load hides the notice. The error is asserted, not filtered.
 */

const NOTICE =
  "The background map didn't load. The land layers still work. Try reloading the page.";

const LIBERTY_STYLE = JSON.stringify({
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#e7eef3" },
    },
  ],
});

test.describe("BASEMAP-ERR-1", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("failed style shows the notice and a later style hides it", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });

    await page.route("**/tiles.openfreemap.org/styles/positron**", async (route) => {
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ error: "style failed" }),
      });
    });
    await page.route("**/tiles.openfreemap.org/styles/liberty**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: LIBERTY_STYLE,
      });
    });
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
      consoleErrors.some((line) =>
        /positron|openfreemap|AJAXError|Failed to fetch|style failed|500/i.test(line),
      ),
      `expected the style failure in the console:\n${consoleErrors.join("\n")}`,
    ).toBe(true);

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("layers-panel")).toBeHidden();
    await page.getByTestId("basemap-option-detailed").click();
    await expect(notice).toBeHidden({ timeout: 20_000 });
  });
});
