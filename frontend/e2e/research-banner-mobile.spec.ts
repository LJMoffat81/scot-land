import { expect, test, type Page } from "@playwright/test";

/**
 * SW-016 / site-watch D2: at ≤768px the research banner is a one-line strip
 * under the header (tap to expand). Must not cover burger, search, or place card.
 */
test.describe("SW-016 mobile research banner strip", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("map banner is a one-line strip under the header; tap expands; no cover", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute("data-strip", "true");
    await expect(banner).toHaveAttribute("data-expanded", "false");
    await expect(banner).toContainText("Research estimate.");

    const toggle = page.getByTestId("research-banner-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");

    const bannerBox = await banner.boundingBox();
    expect(bannerBox).toBeTruthy();
    // One-line strip: short height, not a multi-line card.
    expect(bannerBox!.height).toBeLessThan(52);

    const search = page.locator("#place-query");
    const burger = page.getByTestId("site-nav-menu-btn");
    await expect(search).toBeVisible();
    await expect(burger).toBeVisible();

    const searchBox = await search.boundingBox();
    const burgerBox = await burger.boundingBox();
    expect(searchBox).toBeTruthy();
    expect(burgerBox).toBeTruthy();

    expect(
      overlaps(bannerBox!, searchBox!),
      "collapsed banner must not cover the search field",
    ).toBe(false);
    expect(
      overlaps(bannerBox!, burgerBox!),
      "collapsed banner must not cover the burger menu",
    ).toBe(false);
    // Strip sits under the header (below search row).
    expect(bannerBox!.y).toBeGreaterThanOrEqual(
      searchBox!.y + searchBox!.height - 1,
    );

    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "true");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(banner).toContainText(
      "Annual Ground Rent figures are not published yet",
    );

    const expandedBox = await banner.boundingBox();
    expect(expandedBox).toBeTruthy();
    expect(expandedBox!.height).toBeGreaterThan(bannerBox!.height);
    expect(
      overlaps(expandedBox!, searchBox!),
      "expanded banner must not cover the search field",
    ).toBe(false);
    expect(
      overlaps(expandedBox!, burgerBox!),
      "expanded banner must not cover the burger menu",
    ).toBe(false);

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

    const cardBox = await card.boundingBox();
    const bannerWithCard = await banner.boundingBox();
    expect(cardBox).toBeTruthy();
    expect(bannerWithCard).toBeTruthy();
    expect(
      overlaps(bannerWithCard!, cardBox!),
      "banner must not cover the place card",
    ).toBe(false);
  });
});

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

function overlaps(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}
