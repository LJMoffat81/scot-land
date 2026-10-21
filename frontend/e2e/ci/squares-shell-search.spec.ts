import {
  injectEsriBasemapKey,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


async function openMap(page: Page) {
  await injectEsriBasemapKey(page);
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

test.describe("squares shell", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("full-screen map with prominent search and place card", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.route("**/api/gbp-live**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ enabled: false }),
      });
    });
    await openMap(page);

    await expect(page.locator(".app-shell")).toBeVisible();
    await expect(page.locator("#map")).toBeVisible();
    const search = page.locator("#place-query");
    await expect(search).toBeVisible();
    await expect(search).toHaveAttribute("placeholder", /postcode or place/i);
    await expect(search).not.toHaveAttribute("placeholder", /map reference/i);

    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
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
        }),
      });
    });

    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("place-card-agr-label")).toHaveText(
      "Annual Ground Rent",
    );
    await expect(page.getByTestId("place-card-figure")).toContainText(
      "We're not showing amounts yet while we check our method.",
    );
    // MAP-CARDS: covers-homes only inside the fold, not a top row testid
    await expect(page.getByTestId("place-card-covers-homes")).toHaveCount(0);
    await expect(card.getByText(/£\d/)).toHaveCount(0);
    await expect(card).not.toContainText("£0");
    await expect(card).not.toContainText(/what3words/i);
  });
});

test.describe("squares shell mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("search stays usable on a phone-sized viewport", async ({ page }) => {
    test.setTimeout(60_000);
    await openMap(page);
    const search = page.locator("#place-query");
    await expect(search).toBeVisible();
    const box = await search.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(200);
    const basemap = page.getByTestId("basemap-switcher");
    await expect(basemap).toBeVisible();
    await expect(basemap).toHaveAccessibleName("Aerial map");
    await expect(basemap).toHaveAttribute("aria-pressed", "false");
    await expect(basemap).not.toContainText("Detailed");
    await expect(basemap).not.toContainText(/Satellite/i);
    await expect(
      page.getByRole("button", { name: "Layers", exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "Locate" })).toHaveCount(0);
  });
});
