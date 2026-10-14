import { expect, test, type Locator, type Page } from "@playwright/test";

import { RESEARCH_BANNER_STRIP_COLLAPSED } from "../lib/siteNav";

/**
 * SW-016 — ≤768px research banner is a one-line strip under the header;
 * tap expands. Must not cover burger, search, or place card.
 * Also: open menu keeps Map + About on top; no console errors.
 */
test.describe("SW-016 research banner strip 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("collapsed strip expands and clears burger, search, and place card", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });

    await openMap(page);

    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toHaveAttribute("data-strip", "1");
    await expect(banner).toHaveAttribute("data-expanded", "0");

    const toggle = page.getByTestId("research-banner-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(banner.locator(".research-banner-text")).toHaveText(
      RESEARCH_BANNER_STRIP_COLLAPSED,
    );
    await expect(banner).not.toContainText(
      "Annual Ground Rent figures are not published yet",
    );

    const burger = page.getByTestId("site-nav-menu-btn");
    const search = page.locator("#place-query");
    await expect(burger).toBeVisible();
    await expect(search).toBeVisible();
    await assertBannerClears(banner, burger, "burger menu");
    await assertBannerClears(banner, search, "search field");
    await assertCenterTappable(burger, "burger menu");
    await assertCenterTappable(search, "search field");

    // Menu open: Map and About stay on top (first links, near the top of the panel).
    await burger.click();
    const panel = page.getByTestId("site-nav-panel");
    await expect(panel).toBeVisible();
    const menuLinks = panel.getByRole("link");
    await expect(menuLinks.nth(0)).toHaveText("Map");
    await expect(menuLinks.nth(1)).toHaveText("About");
    const mapBox = await menuLinks.nth(0).boundingBox();
    const aboutBox = await menuLinks.nth(1).boundingBox();
    expect(mapBox, "Map link box").toBeTruthy();
    expect(aboutBox, "About link box").toBeTruthy();
    expect(mapBox!.y, "Map should be near the top").toBeLessThan(200);
    expect(aboutBox!.y, "About should sit under Map").toBeGreaterThan(mapBox!.y);
    expect(aboutBox!.y, "About should stay near the top").toBeLessThan(280);
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();

    // One-line strip: height stays compact while collapsed.
    const collapsedBox = await banner.boundingBox();
    expect(collapsedBox).toBeTruthy();
    expect(collapsedBox!.height, "collapsed strip should be one line").toBeLessThan(
      52,
    );

    // Expand / collapse while the place card is closed (card stacks above the strip).
    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "1");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(banner).toContainText(
      "Annual Ground Rent figures are not published yet",
    );
    await assertBannerClears(banner, burger, "burger with banner expanded");
    await assertBannerClears(banner, search, "search with banner expanded");
    await assertCenterTappable(burger, "burger with banner expanded");
    await assertCenterTappable(search, "search with banner expanded");

    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "0");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(banner.locator(".research-banner-text")).toHaveText(
      RESEARCH_BANNER_STRIP_COLLAPSED,
    );

    await mockPlaceCard(page);
    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    const cardTitle = page.getByTestId("place-card-place");
    const cardClose = page.getByRole("button", { name: "Close place card" });
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(cardTitle).toBeVisible();
    // Tall cards may share y-range with the strip; stacking keeps the card on top.
    await assertCenterTappable(cardTitle, "place card title");
    await assertCenterTappable(cardClose, "place card close");
    await assertBannerClears(banner, burger, "burger with place card open");
    await assertBannerClears(banner, search, "search with place card open");

    expect(
      consoleErrors,
      `console errors on map strip e2e:\n${consoleErrors.join("\n")}`,
    ).toEqual([]);
  });
});

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

async function mockPlaceCard(page: Page) {
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
}

type Box = { x: number; y: number; width: number; height: number };

function overlaps(a: Box, b: Box) {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

/** Banner must not geometrically cover the target. */
async function assertBannerClears(
  banner: Locator,
  target: Locator,
  label: string,
) {
  await expect(banner, "banner").toBeVisible();
  await expect(target, label).toBeVisible();
  const bannerBox = await banner.boundingBox();
  const targetBox = await target.boundingBox();
  expect(bannerBox, "banner box").toBeTruthy();
  expect(targetBox, `${label} box`).toBeTruthy();
  expect(
    overlaps(bannerBox!, targetBox!),
    `${label} overlaps research banner`,
  ).toBe(false);
}

/**
 * Centre of the control must not sit under the research banner.
 * (Other chrome such as the service-busy strip is out of SW-016 scope.)
 */
async function assertCenterTappable(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const hit = document.elementFromPoint(x, y);
    const banner = hit?.closest?.(
      '[data-testid="research-banner"]',
    ) as Element | null;
    const describe = (node: Element | null) => {
      if (!node) return "nothing";
      const id = node.id ? `#${node.id}` : "";
      const cls = (node.getAttribute("class") || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((name) => `.${name}`)
        .join("");
      return `${node.tagName.toLowerCase()}${id}${cls}`;
    };
    return {
      blockedByBanner: !!banner,
      hit: describe(hit),
      x,
      y,
    };
  });
  expect(
    result.blockedByBanner,
    `${label} centre covered by research banner (hit ${result.hit} at ${result.x.toFixed(1)}, ${result.y.toFixed(1)})`,
  ).toBe(false);
}
