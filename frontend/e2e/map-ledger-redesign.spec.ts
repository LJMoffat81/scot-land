import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

test.describe("map ledger redesign", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("Ledger gone; Layers drawer right with legend; place card DZ2022; no £0", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await expect(
      page.getByRole("button", { name: "Ledger", exact: true }),
    ).toHaveCount(0);

    const layersBtn = page.getByRole("button", { name: "Layers", exact: true });
    await expect(layersBtn).toBeVisible();
    await layersBtn.click();

    const tools = page.locator("aside.hud-tools");
    await expect(tools).toBeVisible();
    await expect(tools.getByTestId("layers-panel")).toBeVisible();
    await expect(tools.getByTestId("evidence-tag-legend")).toBeVisible();
    for (const group of ["land", "resources", "nature", "limits", "boundaries"]) {
      await expect(page.getByTestId(`layers-group-${group}`)).toBeVisible();
    }
    await expect(tools.getByTestId("ledger-panel")).toHaveCount(0);

    // Drawer is on the right (not covering Find-a-place on the left).
    const toolsBox = await tools.boundingBox();
    const find = page.locator("aside.hud-scotland");
    const findBox = await find.boundingBox();
    expect(toolsBox).toBeTruthy();
    expect(findBox).toBeTruthy();
    expect(toolsBox!.x).toBeGreaterThan(findBox!.x);

    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.8609,
          lng: -4.2514,
          place_label: "Test place",
          council_name: "Glasgow City",
          data_zone: {
            status: "ok",
            code: "S01014567",
            name: "City Centre South",
            vintage: 2022,
          },
          intermediate_zone: {
            status: "ok",
            code: "S02002645",
            name: "City Centre",
          },
          agr_rows: [
            {
              id: "surface",
              label: "Surface land",
              tag: "proxy",
              status: "in_progress",
              applies: true,
              of_which: [
                { id: "planning_uplift", label: "of which: planning uplift" },
              ],
            },
          ],
          constraints: [{ id: "flood", label: "Flood", applies: true }],
          holder: { status: "private_not_shown", label: "private, not shown" },
          layers: [],
          links: [
            { id: "methodology", label: "How we value land", url: "/methodology" },
          ],
        }),
      });
    });
    await page.route("**/layers/context/data-zones/at**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01014567",
          name: "City Centre South",
          vintage: 2022,
        }),
      });
    });

    await page.locator("#place-query").fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("place-card-data-zone")).toContainText(
      "S01014567",
    );
    await expect(page.getByTestId("place-card-dz-vintage")).toContainText(
      "DZ2022",
    );
    await expect(page.getByTestId("place-card-value")).toBeVisible();
    await expect(page.getByTestId("place-card-limits")).toBeVisible();
    await expect(page.getByTestId("place-card-how-we-value")).toBeVisible();

    const publicBits = [
      await card.innerText(),
      await tools.innerText(),
      await page.locator("aside.hud-scotland").innerText(),
    ].join("\n");
    expect(publicBits).not.toContain("£0");
    expect(publicBits).not.toMatch(/ECONOMIC_RULES|Placeholders are not|NESTED|REPORTED/i);
  });
});
