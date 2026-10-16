import { expect, test, type Page } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  ensureMapZoomAtLeast,
  openLayers,
  openMap,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";

/**
 * SEPA-FLOOD-2 — river and coastal medium-likelihood images from SEPA.
 * Requests go to map.sepa.org.uk. The credit and beta service note show in Layers.
 */

const CREDIT =
  "©SEPA 2025; this SEPA product is licensed under the Open Government Licence version 3.0.";

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

async function stubSepaImages(page: Page, seen: string[]) {
  await page.route("**/map.sepa.org.uk/**", async (route) => {
    seen.push(route.request().url());
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: PNG,
    });
  });
}

for (const width of [1280, 390] as const) {
  test.describe(`SEPA-FLOOD-2 @ ${width}`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } });

    test("river and coastal images request SEPA and show the credit", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const seen: string[] = [];
      await stubMapCardsBackend(page);
      await stubSepaImages(page, seen);
      await openMap(page);
      await ensureMapZoomAtLeast(page, 8);
      await openLayers(page);
      await ensureLayersGroupOpen(page, "land");

      await expect(page.getByTestId("layer-toggle-flood")).toHaveCount(0);
      await expect(page.getByTestId("flood-kind")).toHaveCount(0);

      const river = page.getByTestId("layer-toggle-flood_river");
      const coastal = page.getByTestId("layer-toggle-flood_coastal");
      await expect(river).toBeVisible();
      await expect(coastal).toBeVisible();
      await expect(river).toHaveAttribute("aria-checked", "false");
      await expect(coastal).toHaveAttribute("aria-checked", "false");
      await expect(page.getByTestId("layer-desc-flood_river")).toHaveText(
        "beta service",
      );
      await expect(page.getByTestId("layer-desc-flood_coastal")).toHaveText(
        "beta service",
      );

      await river.click();
      await coastal.click();
      await ensureMapZoomAtLeast(page, 8);
      await expect(page.getByTestId("layer-source-caption-flood_river")).toHaveText(
        CREDIT,
      );
      await expect(
        page.getByTestId("layer-source-caption-flood_coastal"),
      ).toHaveText(CREDIT);

      const layerParam = (url: string) =>
        new URL(url).searchParams.get("layers") ?? "";
      await expect
        .poll(() => seen.filter((url) => layerParam(url) === "show:1").length, {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
      await expect
        .poll(() => seen.filter((url) => layerParam(url) === "show:7").length, {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
      for (const url of seen) {
        const parsed = new URL(url);
        expect(parsed.hostname).toBe("map.sepa.org.uk");
        expect(parsed.pathname).toContain(
          "/server/rest/services/Open/Flood_Maps/MapServer/export",
        );
      }

      await expect(page.getByTestId("layers-panel")).not.toContainText(/£/);
      assertConsoleClean(gate);
    });
  });
}
