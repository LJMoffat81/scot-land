import { expect, test, type Page } from "@playwright/test";

const OUT_OF_SCOTLAND_LINE =
  "This spot is outside Scotland's land map. Tap on land to see a place.";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

test.describe("site-watch D3 sea click", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("click at sea shows one plain line, not No data rows", async ({
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

    // North Sea point — no Scottish data zone.
    const lat = 56.5;
    const lng = -1.5;

    await page.route("**/layers/context/data-zones/at**", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            error: "no_data_zone_at_point",
            lat,
            lon: lng,
          },
        }),
      });
    });

    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat,
          lng,
          place_label: null,
          council_name: null,
          data_zone: {
            status: "miss",
            code: null,
            name: null,
            vintage: null,
            note: "No Scottish data zone contains this point (e.g. at sea).",
          },
          intermediate_zone: { status: "no_data", name: null, note: null },
          square_reference: "Scot-LAND square reference 0,0",
          agr_rows: [
            {
              id: "surface",
              label: "Land",
              tag: "proxy",
              status: "coming_soon",
              applies: true,
            },
          ],
          constraints: [],
          layers: [],
          links: [],
        }),
      });
    });

    await openMap(page);

    await page.locator("#place-query").fill(`${lat}, ${lng}`);
    await page.locator(".hud-search-go").click();

    const line = page.getByTestId("place-card-out-of-scotland");
    await expect(line).toBeVisible({ timeout: 30_000 });
    await expect(line).toHaveText(OUT_OF_SCOTLAND_LINE);

    const card = page.getByTestId("place-card");
    await expect(card.getByTestId("place-card-value")).toHaveCount(0);
    await expect(card.getByTestId("place-card-limits")).toHaveCount(0);
    await expect(card.getByTestId("place-card-data-zone")).toHaveCount(0);
    await expect(card.getByText("No data")).toHaveCount(0);
    await expect(card.locator(".place-card-field")).toHaveCount(0);

    expect(
      consoleErrors,
      `console errors on sea click:\n${consoleErrors.join("\n")}`,
    ).toEqual([]);
  });
});
