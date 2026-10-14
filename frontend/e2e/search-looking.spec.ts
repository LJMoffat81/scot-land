import { expect, test, type Page } from "@playwright/test";

const POSTCODE = "EH1 1YZ";

async function stubAgrSearch(page: Page) {
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        routers: {
          "api.agr_routes": { loaded: true },
          "api.platform_routes": { loaded: true },
        },
      }),
    });
  });

  await page.route("**/backend/place**", async (route) => {
    const url = new URL(route.request().url());
    const q = (url.searchParams.get("q") || "").toUpperCase().replace(/\s+/g, " ");
    // Brief delay so the Looking… pending row can render before results land.
    await new Promise((r) => setTimeout(r, 80));
    if (q.includes("EH1")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          kind: "postcode",
          postcode: POSTCODE,
          lat: 55.952,
          lng: -3.189,
          label: POSTCODE,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "none", note: "No matches" }),
    });
  });

  await page.route("**/backend/postcode/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        postcode: { postcode: POSTCODE },
        lat: 55.952,
        lng: -3.189,
        square: { lat: 55.952, lng: -3.189 },
      }),
    });
  });

  await page.route("**/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.952,
        lng: -3.189,
        place_label: "Edinburgh Old Town",
        council_name: "City of Edinburgh",
        data_zone: {
          status: "ok",
          code: "S01008677",
          name: "Old Town",
          vintage: 2022,
        },
        intermediate_zone: { status: "ok", name: "Old Town and Canongate" },
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
}

test.describe("search dropdown Looking…", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("selecting a postcode clears Looking… within 1s", async ({ page }) => {
    test.setTimeout(90_000);
    await stubAgrSearch(page);

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const search = page.locator("#place-query");
    await search.waitFor();

    await search.fill(POSTCODE);
    const option = page.getByRole("option", { name: POSTCODE });
    await expect(option).toBeVisible({ timeout: 10_000 });
    await option.click();

    await page.waitForTimeout(1000);
    await expect(page.getByText("Looking…")).toHaveCount(0);
    await expect(page.locator(".search-suggest-note")).toHaveCount(0);
  });

  test("Escape and empty results clear Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    await stubAgrSearch(page);

    await page.goto("/");
    await page.locator("#place-query").waitFor();
    const search = page.locator("#place-query");

    await search.fill("zzz");
    await expect(page.getByText("No matches")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Looking…")).toHaveCount(0);

    await search.fill("EH1");
    await expect(page.getByRole("option", { name: POSTCODE })).toBeVisible({
      timeout: 10_000,
    });
    await search.press("Escape");
    await expect(page.getByText("Looking…")).toHaveCount(0);
    await expect(page.locator(".search-suggest")).toHaveCount(0);
  });
});
