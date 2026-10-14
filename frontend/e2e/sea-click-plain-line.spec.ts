import { expect, test, type Page } from "@playwright/test";

const OUT_OF_SCOTLAND_LINE =
  "This spot is outside Scotland's land map. Tap on land to see a place.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

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
    const resourceFails: Array<{ url: string; status: number }> = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });
    page.on("response", (response) => {
      const status = response.status();
      if (status === 404 || status === 503) {
        resourceFails.push({ url: response.url(), status });
      }
    });

    // Stub map chrome deps (same pattern as site-nav-banner) so CI e2e
    // fails on real console/page errors, not missing-API noise.
    await page.route("**/backend/health**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
    });
    await page.route("**/backend/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
    });
    await page.route("**/backend/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
    });
    await page.route("**/backend/layers/open/data-zones**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
    });
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
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

    // Intentional sea miss is the only allowed 404; nothing may 503.
    const unexpectedResourceFails = resourceFails.filter((fail) => {
      if (fail.status === 404 && /data-zones\/at/i.test(fail.url)) {
        return false;
      }
      return true;
    });
    expect(
      unexpectedResourceFails,
      `unexpected HTTP 404/503:\n${unexpectedResourceFails
        .map((f) => `${f.status} ${f.url}`)
        .join("\n")}`,
    ).toEqual([]);

    const meaningful = consoleErrors.filter((text) => {
      if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
        return false;
      }
      if (
        /Failed to load resource: the server responded with a status of (404|503)/i.test(
          text,
        )
      ) {
        // Chromium's URL-less resource line is OK only when every recorded
        // 404/503 was the intentional sea DZ miss.
        if (!/https?:\/\//i.test(text) && unexpectedResourceFails.length === 0) {
          return false;
        }
        return true;
      }
      return true;
    });
    expect(
      meaningful,
      `console errors on sea click:\n${meaningful.join("\n")}`,
    ).toEqual([]);
  });
});
