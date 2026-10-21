
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, openMap, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * COPY-SEA-1 — a map click at sea shows the signed-off line and both controls.
 * The line has no £ and none of the banned words.
 */

const SEA_LINE =
  "We only cover land so far. Scotland's sea rents (offshore wind, oil and gas, fish farms and seabed) will come later as their own map layer.";

const BANNED = [
  /natural capital/i,
  /\bledger\b/i,
  /\bheadline\b/i,
  /\bshadow\b/i,
  /\byield\b/i,
  /what3words/i,
  /\bneighbourhood\b/i,
] as const;

const SEA = { lat: 56.5, lng: -1.5 };

function seaMissBody() {
  return {
    contract: "place_card_v1",
    lat: SEA.lat,
    lng: SEA.lng,
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
    square_reference: null,
    agr_rows: [],
    constraints: [],
    layers: [],
    links: [],
  };
}

async function stubSeaMiss(page: Page) {
  await stubMapCardsBackend(page);
  await page.route("**/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: { error: "no_data_zone_at_point", lat: SEA.lat, lon: SEA.lng },
      }),
    });
  });
  const body = JSON.stringify(seaMissBody());
  await page.route("**/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body,
    });
  });
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body,
    });
  });
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`COPY-SEA-1 (${viewport.width})`, () => {
    test.use({ viewport });

    test("click at sea shows the sea line and both controls", async ({
      page,
      gate,
    }) => {
      test.setTimeout(90_000);
      // Intentional data-zones/at 404 for the sea miss stub.
      gate.expectError({
        urlPath: "/backend/layers/context/data-zones/at",
        status: 404,
        count: 1,
      });
      await stubSeaMiss(page);
      await openMap(page);
      await waitForMap(page);

      await page.evaluate(({ lat, lng }) => {
        const map = (
          window as unknown as {
            __map?: {
              fire(type: string, ev: object): void;
              project(lngLat: { lng: number; lat: number }): {
                x: number;
                y: number;
              };
            };
          }
        ).__map;
        if (!map) throw new Error("window.__map missing");
        const lngLat = { lng, lat };
        map.fire("click", {
          lngLat,
          point: map.project(lngLat),
          originalEvent: new MouseEvent("click"),
        });
      }, SEA);

      const line = page.getByTestId("place-card-sea-line-text");
      await expect(line).toBeVisible({ timeout: 30_000 });
      await expect(line).toHaveText(SEA_LINE);
      const text = (await line.textContent()) ?? "";
      expect(text).not.toContain("£");
      for (const pattern of BANNED) {
        expect(text).not.toMatch(pattern);
      }

      await expect(page.getByTestId("place-card-place")).toHaveText("Out at sea");
      await expect(page.getByTestId("place-card-show-scotland")).toHaveText(
        "Show me Scotland",
      );
      const roadmap = page.getByTestId("place-card-see-roadmap");
      await expect(roadmap).toHaveText("See the roadmap");
      await expect(roadmap).toHaveAttribute("href", "/roadmap");
    });
  });
}
