import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

test.describe("w3w-style shell", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("full-screen map with prominent search and stub place card", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await expect(page.locator(".app-shell.w3w-shell")).toBeVisible();
    await expect(page.locator("#map")).toBeVisible();
    const search = page.locator("#place-query");
    await expect(search).toBeVisible();
    await expect(search).toHaveAttribute(
      "placeholder",
      /postcode|place|coordinates/i,
    );

    // Coordinate search opens the stub place card (no AGR £ / tax copy as the headline figure).
    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.locator("aside.place-card-stub");
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(card.getByRole("heading", { level: 2 })).toContainText(
      /55\.8609/,
    );
    await expect(card.getByText(/not shown on the public map yet/i)).toBeVisible();
    await expect(card.getByText(/£\d/)).toHaveCount(0);
  });
});

test.describe("w3w-style shell mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("search stays usable on a phone-sized viewport", async ({ page }) => {
    test.setTimeout(60_000);
    await openMap(page);
    const search = page.locator("#place-query");
    await expect(search).toBeVisible();
    const box = await search.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThan(200);
    await expect(page.getByRole("button", { name: "Satellite" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Layers", exact: true }),
    ).toHaveCount(0);
  });
});
