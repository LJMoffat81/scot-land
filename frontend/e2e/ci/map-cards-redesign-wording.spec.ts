import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  BANNED_VISIBLE,
  countMatches,
  ensureLayersGroupOpen,
  ensureMapZoomAtLeast,
  openLayers,
  openMap,
  openPlaceViaCoords,
  PRE_POUND,
  stubMapCardsBackend,
  visibleMapText,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS checks 8–10, 12, 20–22, 36 — say-it-once, wording, no-match,
 * map at rest, certainty key, captions, roadmap, default view.
 */

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`MAP-CARDS wording (${viewport.width})`, () => {
    test.use({ viewport });

    test("8 say it once (a–g); 9 wording guard", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openPlaceViaCoords(page);

      const header = page.getByTestId("place-card-header");
      await expect(header).toContainText(/not published yet|not showing amounts/i);
      const headerText = await header.innerText();
      expect(
        countMatches(headerText, /not published yet|not showing amounts/i),
      ).toBeGreaterThanOrEqual(1);

      const body = await visibleMapText(page);
      expect(countMatches(body, /coming soon/i)).toBe(0);
      expect(countMatches(body, /not an official valuation/i)).toBe(1);
      await expect(page.getByTestId("place-card-footer")).toContainText(
        "not an official valuation",
      );

      // (d) under homes only ≤1 — open fold then count
      const parts = page.getByTestId("place-card-parts");
      if (!(await parts.getAttribute("open"))) {
        await parts.locator("summary").click();
      }
      const withFold = await visibleMapText(page);
      expect(countMatches(withFold, /under homes only/i)).toBeLessThanOrEqual(1);

      // (e) research banner hidden or collapsed while card open
      const banner = page.getByTestId("research-banner");
      if ((await banner.count()) > 0) {
        const box = await banner.boundingBox();
        if (box) expect(box.height).toBeLessThanOrEqual(48);
      }

      // (f) no OGL spam with no RoS layer
      expect(countMatches(withFold, /Open Government Licence|\bOGL\b/)).toBe(0);
      await expect(page.getByTestId("map-all-sources")).toBeVisible();

      // (g) no zone codes / of which / wrong Leith→Edinburgh pattern for this fixture
      expect(withFold).not.toMatch(/S0[12]\d{6}/);
      expect(withFold).not.toMatch(/\bof which\b/i);

      expect(withFold).not.toMatch(BANNED_VISIBLE);
      expect(withFold).not.toContain("£");
      expect(withFold).not.toMatch(/-?\d+\.\d{4,},\s*-?\d+\.\d{4,}/);

      await expect(page.getByTestId("place-card-figure")).toContainText(PRE_POUND);
      assertConsoleClean(gate);
    });

    test("10 no-match: pin 0, card closed, search-no-match visible", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      // Empty place matches from stub.
      await page.route("**/backend/place**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ kind: "places", matches: [] }),
        });
      });
      await openMap(page);
      await page.locator("#place-query").fill("Zzzqxx place that does not exist");
      await page.locator(".hud-search-go").click();
      await expect(page.getByTestId("search-no-match")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByTestId("place-card")).toHaveCount(0);
      await expect(page.locator(".maplibregl-marker")).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("12 map at rest: no density switch; councils on; builtup not a switch", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      await expect(page.getByTestId("layer-toggle-builtup_mask")).toHaveCount(0);
      await expect(page.getByTestId("layer-toggle-dz_pop_density")).toHaveCount(0);
      await expect(
        page.getByRole("switch", { name: /people per km|population density/i }),
      ).toHaveCount(0);
      await expect(page.getByTestId("layer-toggle-councils")).toHaveAttribute(
        "aria-checked",
        "true",
      );
      await expect(page.getByTestId("layer-toggle-data_zones")).toHaveAttribute(
        "aria-checked",
        "false",
      );
      // No parcel / plot switch
      await expect(page.getByTestId("layer-toggle-boundaries")).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("20 certainty key; 21 source caption; 22 no coming-soon in Layers", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await ensureMapZoomAtLeast(page, 11);
      await openLayers(page);

      const panel = page.getByTestId("layers-panel");
      await expect(panel).not.toContainText(/coming soon/i);
      // LAYERS-NAV-1 placeholders use the roadmap tag "Coming later".
      // Live switches still must not.
      const switchText = await panel.getByRole("switch").allInnerTexts();
      for (const line of switchText) {
        expect(line).not.toMatch(/coming soon|coming later/i);
      }

      await ensureLayersGroupOpen(page, "land");
      await page.getByTestId("layer-toggle-1").click();
      const legend = page.getByTestId("layer-inline-legend-1");
      await expect(legend).toBeVisible();
      await expect(legend).toContainText("Striped = less sure");
      await expect(legend).toContainText("No figure here");
      await expect(legend).not.toContainText("Paler = less sure");
      await expect(legend).not.toContainText(/Hatched/i);
      await expect(legend).toContainText("Lower");
      await expect(legend).toContainText("Higher");
      await expect(page.getByTestId("layer-source-caption-1")).toBeVisible();
      const caption = await page.getByTestId("layer-source-caption-1").innerText();
      expect(caption).toMatch(/·/);

      const roadmap = page.getByTestId("map-layers-roadmap-link").locator("a");
      await expect(roadmap).toHaveAttribute("href", "/roadmap#map-layers");
      await page.goto("/roadmap#map-layers");
      await expect(page.getByTestId("roadmap-map-layers")).toBeVisible();
      assertConsoleClean(gate);
    });

    test("36 default view prompt when gbp-live off", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await openMap(page);
      await expect(page.getByTestId("map-rest-prompt")).toHaveText(
        "Search a place or pick a layer.",
      );
      await expect(page.getByTestId("map-rest-prompt")).toHaveCount(1);
      await openLayers(page);
      await ensureLayersGroupOpen(page, "land");
      await expect(page.getByTestId("layer-toggle-1")).toHaveAttribute(
        "aria-checked",
        "false",
      );
      await expect(page.getByTestId("layer-toggle-councils")).toHaveAttribute(
        "aria-checked",
        "true",
      );
      assertConsoleClean(gate);
    });
  });
}

test.describe("MAP-CARDS default view gbp-live on (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("36b AGR on when gbp live; 36c deep link wins", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page, { gbpLive: true });
    await openMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "land");
    await expect(page.getByTestId("layer-toggle-1")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    // Deep link overrides — access to services + place, no AGR auto-add
    await stubMapCardsBackend(page, { gbpLive: true });
    await page.goto("/?layers=access_services&place=S01014567&lat=55.86&lng=-4.25");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    await openLayers(page);
    await ensureLayersGroupOpen(page, "nature");
    await ensureLayersGroupOpen(page, "land");
    await expect(page.getByTestId("layer-toggle-access_services")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await expect(page.getByTestId("layer-toggle-1")).toHaveAttribute(
      "aria-checked",
      "false",
    );
    assertConsoleClean(gate);
  });
});
