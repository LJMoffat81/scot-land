import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * SW-016 — ≤768px research banner is a one-line strip under the header;
 * tap expands. Must not cover burger, search, or place card.
 */
test.describe("SW-016 research banner strip 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("collapsed strip expands and clears burger, search, and place card", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toHaveAttribute("data-strip", "1");
    await expect(banner).toHaveAttribute("data-expanded", "0");

    const toggle = page.getByTestId("research-banner-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(banner).toContainText("Research estimate.");
    await expect(banner).not.toContainText(
      "Annual Ground Rent figures are not published yet",
    );

    const burger = page.getByTestId("site-nav-menu-btn");
    const search = page.locator("#place-query");
    await expect(burger).toBeVisible();
    await expect(search).toBeVisible();
    await assertUncovered(burger, "burger menu");
    await assertUncovered(search, "search field");

    // One-line strip: height stays compact while collapsed.
    const collapsedBox = await banner.boundingBox();
    expect(collapsedBox).toBeTruthy();
    expect(collapsedBox!.height, "collapsed strip should be one line").toBeLessThan(
      52,
    );

    await mockPlaceCard(page);
    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    const cardTitle = page.getByTestId("place-card-place");
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(cardTitle).toBeVisible();
    await assertUncovered(cardTitle, "place card title (collapsed banner)");
    await assertUncovered(burger, "burger with place card open");
    await assertUncovered(search, "search with place card open");

    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "1");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(banner).toContainText(
      "Annual Ground Rent figures are not published yet",
    );

    // Expanded strip stays under the header — must not paint over chrome or card.
    const expandedBox = await banner.boundingBox();
    const cardBox = await card.boundingBox();
    expect(expandedBox).toBeTruthy();
    expect(cardBox).toBeTruthy();
    if (expandedBox && cardBox) {
      expect(
        expandedBox.y + expandedBox.height,
        "expanded banner must end above the place card",
      ).toBeLessThanOrEqual(cardBox.y + 1);
    }

    await assertUncovered(burger, "burger with banner expanded");
    await assertUncovered(search, "search with banner expanded");
    await assertUncovered(cardTitle, "place card title with banner expanded");

    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "0");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
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

async function assertUncovered(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    const points = [
      { x: box.left + box.width / 2, y: box.top + box.height / 2 },
      { x: box.left + 2, y: box.top + 2 },
      { x: box.right - 2, y: box.top + 2 },
      { x: box.left + 2, y: box.bottom - 2 },
      { x: box.right - 2, y: box.bottom - 2 },
    ];
    const describe = (node: Element) => {
      const id = node.id ? `#${node.id}` : "";
      const cls = (node.getAttribute("class") || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((name) => `.${name}`)
        .join("");
      return `${node.tagName.toLowerCase()}${id}${cls}`;
    };
    const covers: string[] = [];
    for (const point of points) {
      const hit = document.elementFromPoint(point.x, point.y);
      if (!hit || !el.contains(hit)) {
        const name = hit ? describe(hit) : "nothing";
        covers.push(`${name} at (${point.x.toFixed(1)}, ${point.y.toFixed(1)})`);
      }
    }
    return {
      visibility: style.visibility,
      opacity: Number(style.opacity),
      display: style.display,
      left: box.left,
      top: box.top,
      right: box.right,
      bottom: box.bottom,
      width: box.width,
      height: box.height,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      covers,
    };
  });

  expect(result.visibility, label).not.toBe("hidden");
  expect(result.opacity, label).toBeGreaterThan(0);
  expect(result.display, label).not.toBe("none");
  expect(result.width, `${label} has no area`).toBeGreaterThan(0);
  expect(result.height, `${label} has no area`).toBeGreaterThan(0);
  expect(result.left, `${label} is outside the viewport`).toBeGreaterThanOrEqual(0);
  expect(result.top, `${label} is outside the viewport`).toBeGreaterThanOrEqual(0);
  expect(result.right, `${label} is outside the viewport`).toBeLessThanOrEqual(
    result.innerWidth,
  );
  expect(result.bottom, `${label} is outside the viewport`).toBeLessThanOrEqual(
    result.innerHeight,
  );
  expect(result.covers, `${label} is covered by ${result.covers.join("; ")}`).toEqual(
    [],
  );
}
