import { expect, test, type Page } from "@playwright/test";

const ROUTES: Array<{ path: string; current: string }> = [
  { path: "/", current: "Map" },
  { path: "/about", current: "About" },
  { path: "/methodology", current: "How it works" },
  { path: "/data", current: "Data & sources" },
  { path: "/developers", current: "Downloads & API" },
];

/** Collect console errors / pageerror for every test (data-page.spec.ts pattern). */
const consoleErrors: string[] = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });

  // Stub API so ContentPageFooter / map health polls do not 503 without a backend.
  // Specs may override these with more specific routes registered later.
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/downloads/manifest.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ generated_at: "2026-01-01", bundles: [] }),
    });
  });
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (url.includes("/place?") || url.endsWith("/place")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "{}",
    });
  });
});

test.afterEach(() => {
  const meaningful = consoleErrors.filter(
    (text) =>
      !/Failed to load resource: the server responded with a status of (404|503)/i.test(
        text,
      ),
  );
  expect(
    meaningful,
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
});

async function openAttributionIfCollapsed(page: Page) {
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  const collapsed = await attrib.evaluate((el) => {
    const compact = el.classList.contains("maplibregl-compact");
    const shown = el.classList.contains("maplibregl-compact-show");
    const inner = el.querySelector(".maplibregl-ctrl-attrib-inner");
    if (!inner) return false;
    const style = getComputedStyle(inner);
    const hidden = style.display === "none" || style.visibility === "hidden";
    return (compact && !shown) || hidden;
  });
  if (!collapsed) return;
  await page.locator(".maplibregl-ctrl-attrib-button").click({ timeout: 10_000 });
}

test.describe("site nav + research banner (rewrite PR1)", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  for (const route of ROUTES) {
    test(`${route.path} has shared nav and one banner`, async ({ page }) => {
      await page.goto(route.path);
      if (route.path === "/") {
        await page.locator(".maplibregl-canvas").waitFor();
      }
      const nav = page.getByTestId("site-nav");
      await expect(nav).toBeVisible();
      await expect(
        nav.getByRole("link", { name: route.current, exact: true }),
      ).toHaveAttribute("aria-current", "page");
      for (const label of [
        "Map",
        "About",
        "How it works",
        "Data & sources",
        "Downloads & API",
      ]) {
        await expect(
          nav.getByRole("link", { name: label, exact: true }),
        ).toBeVisible();
      }
      await expect(page.getByTestId("research-banner")).toHaveCount(1);
      await expect(page.getByTestId("research-banner")).toContainText(
        "Research estimate.",
      );
      await expect(page.getByTestId("research-banner")).toContainText(
        "Annual Ground Rent figures are not published yet",
      );
      await expect(page.locator("body")).not.toContainText("not a rates bill");
    });
  }

  test("mobile map nav becomes hamburger at 600px", async ({ page }) => {
    await page.setViewportSize({ width: 600, height: 800 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await expect(page.getByTestId("site-nav-menu-btn")).toBeVisible();
    // Designer live-check: burger must start closed (not covering banner/map).
    await expect(page.getByTestId("site-nav-panel")).toBeHidden();
    await page.getByTestId("site-nav-menu-btn").click();
    await expect(page.getByTestId("site-nav-panel")).toBeVisible();
    await expect(
      page.getByTestId("site-nav-panel").getByRole("link", { name: "About" }),
    ).toBeVisible();
  });

  test("page titles", async ({ page }) => {
    await page.goto("/methodology");
    await expect(page).toHaveTitle(/How it works \| Scot-LAND/);
    await page.goto("/data");
    await expect(page).toHaveTitle(/Data & sources \| Scot-LAND/);
    await page.goto("/about");
    await expect(page).toHaveTitle(/About \| Scot-LAND/);
  });
});

test.describe("site-watch PR A — nav visible at desktop widths", () => {
  for (const width of [1024, 1280, 1366, 1440] as const) {
    test(`Map / About / How it works visible at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor();
      const nav = page.getByTestId("site-nav");
      await expect(nav).toBeVisible();
      for (const label of ["Map", "About", "How it works"] as const) {
        const link = nav.getByRole("link", { name: label, exact: true });
        await expect(link).toBeVisible();
        const box = await link.boundingBox();
        expect(box, `${label} at ${width}`).toBeTruthy();
        if (!box) continue;
        // Must not sit under the search dock (two-row ≤1366; centred above).
        const search = page.locator(".hud-search-dock");
        const searchBox = await search.boundingBox();
        if (searchBox) {
          const overlapX =
            box.x < searchBox.x + searchBox.width &&
            box.x + box.width > searchBox.x;
          const overlapY =
            box.y < searchBox.y + searchBox.height &&
            box.y + box.height > searchBox.y;
          expect(
            overlapX && overlapY,
            `${label} must not overlap search at ${width}`,
          ).toBeFalsy();
        }
      }
      if (width <= 1440) {
        // SW-010: search sits on a second row below the nav links.
        const searchBox = await page.locator(".hud-search-dock").boundingBox();
        const howBox = await nav
          .getByRole("link", { name: "How it works", exact: true })
          .boundingBox();
        expect(searchBox && howBox).toBeTruthy();
        if (searchBox && howBox) {
          expect(searchBox.y).toBeGreaterThan(howBox.y + howBox.height - 4);
          // Link must not be covered by search (elementFromPoint at link centre).
          const mid = {
            x: howBox.x + howBox.width / 2,
            y: howBox.y + howBox.height / 2,
          };
          const hit = await page.evaluate(({ x, y }) => {
            const el = document.elementFromPoint(x, y);
            return el?.closest("a")?.textContent?.trim() ?? el?.tagName ?? "none";
          }, mid);
          expect(hit).toBe("How it works");
        }
      }
    });
  }
});

test.describe("site-watch PR A — SW-013 downloads moved note", () => {
  test("/developers?moved=1 shows Downloads has moved here", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/developers?moved=1#downloads");
    await expect(page.getByTestId("developers-moved-note")).toHaveText(
      "Downloads has moved here.",
    );
  });

  test("/developers without moved=1 hides the note", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/developers");
    await expect(page.getByTestId("developers-moved-note")).toHaveCount(0);
  });
});

test.describe("site-watch PR A — SW-014 suggest click at 1280", () => {
  test("click suggestion for EH1 1YZ opens place card", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.route("**/backend/place**", async (route) => {
      const url = new URL(route.request().url());
      const q = (url.searchParams.get("q") || "").toUpperCase();
      if (q.includes("EH1")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            kind: "places",
            matches: [
              {
                label: "EH1 1YZ, Edinburgh",
                lat: 55.9508,
                lng: -3.1875,
              },
              {
                label: "EH1 1AA, Edinburgh",
                lat: 55.9533,
                lng: -3.1883,
              },
            ],
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
    });
    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.9508,
          lng: -3.1875,
          place_label: "Edinburgh, Old Town",
          council_name: "City of Edinburgh",
          data_zone: {
            status: "ok",
            code: "S01008677",
            name: "Old Town",
            vintage: 2022,
          },
          intermediate_zone: {
            status: "ok",
            code: "S02001622",
            name: "Old Town, Princes Street and Leith Street",
          },
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

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    // Dismiss research banner if it still overlaps the search row.
    const dismiss = page.getByTestId("research-banner-dismiss");
    if (await dismiss.isVisible().catch(() => false)) {
      await dismiss.click();
    }
    const input = page.locator("#place-query");
    await input.fill("EH1 1YZ");
    // Wait for debounce (250ms) + suggest response.
    const first = page.locator("#place-suggestions button").first();
    await expect(first).toBeVisible({ timeout: 20_000 });
    await expect(first).toContainText(/EH1/i);

    // Suggestion must sit above the research banner (clickable).
    const suggestBox = await first.boundingBox();
    const bannerBox = await page.getByTestId("research-banner").boundingBox();
    expect(suggestBox).toBeTruthy();
    if (suggestBox && bannerBox) {
      const mid = {
        x: suggestBox.x + suggestBox.width / 2,
        y: suggestBox.y + suggestBox.height / 2,
      };
      const hit = await page.evaluate(({ x, y }) => {
        const el = document.elementFromPoint(x, y);
        return el?.closest("button")?.textContent?.trim() ?? el?.tagName ?? "none";
      }, mid);
      expect(hit).toMatch(/EH1/i);
    }

    await first.click();
    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 30_000,
    });
    // Intro collapses while the card is open.
    await expect(page.locator(".app-shell")).toHaveClass(/place-open/);
    await expect(page.locator(".hud-scotland-job")).toBeHidden();

    // Item 12: restore Find a place intro when the card closes.
    await page.getByRole("button", { name: "Close place card" }).click();
    await expect(page.getByTestId("place-card")).toHaveCount(0);
    await expect(page.locator(".app-shell")).not.toHaveClass(/place-open/);
    await expect(page.locator(".hud-scotland-job")).toBeVisible();
    await expect(page.locator(".hud-scotland-job")).toHaveText("Find a place");
  });
});

test.describe("site-watch PR A — SW-011 mobile nav backdrop", () => {
  for (const path of ["/data", "/developers"] as const) {
    test(`${path}: closed menu covers nothing; open has backdrop`, async ({
      page,
    }) => {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(path);
      const h1 = page.locator("h1").first();
      const banner = page.getByTestId("research-banner");
      await expect(h1).toBeVisible();
      await expect(banner).toBeVisible();

      await expect(page.getByTestId("site-nav-panel")).toBeHidden();
      await expect(page.getByTestId("site-nav-backdrop")).toHaveCount(0);

      // Closed panel must not sit over the H1 / banner.
      const h1Box = await h1.boundingBox();
      const bannerBox = await banner.boundingBox();
      expect(h1Box).toBeTruthy();
      expect(bannerBox).toBeTruthy();
      const midH1 = h1Box
        ? { x: h1Box.x + h1Box.width / 2, y: h1Box.y + h1Box.height / 2 }
        : null;
      if (midH1) {
        const top = await page.evaluate(
          ({ x, y }) => {
            const el = document.elementFromPoint(x, y);
            return el?.closest("h1") ? "h1" : el?.tagName ?? "none";
          },
          midH1,
        );
        expect(top).toBe("h1");
      }

      await page.getByTestId("site-nav-menu-btn").click();
      await expect(page.getByTestId("site-nav-panel")).toBeVisible();
      await expect(page.getByTestId("site-nav-backdrop")).toBeVisible();

      await page.getByTestId("site-nav-backdrop").click({ force: true });
      await expect(page.getByTestId("site-nav-panel")).toBeHidden();
      await expect(page.getByTestId("site-nav-backdrop")).toHaveCount(0);

      await page.getByTestId("site-nav-menu-btn").click();
      await expect(page.getByTestId("site-nav-panel")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(page.getByTestId("site-nav-panel")).toBeHidden();
    });
  }
});

test.describe("site-watch PR A — map footer + mobile banner", () => {
  test("map footer wording and licences link", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const line = page.getByTestId("map-footer-line");
    await expect(line).toHaveText(
      "Research estimate · Open data · Sources and licences",
    );
    await expect(
      line.getByRole("link", { name: "Sources and licences" }),
    ).toHaveAttribute("href", "/data#licences");
    await expect(page.getByTestId("research-banner")).toHaveCount(1);
  });

  test("390px banner does not cover search", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const input = page.locator("#place-query");
    await expect(input).toBeVisible();
    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible();
    const inputBox = await input.boundingBox();
    const bannerBox = await banner.boundingBox();
    expect(inputBox).toBeTruthy();
    expect(bannerBox).toBeTruthy();
    if (inputBox && bannerBox) {
      const overlapY =
        inputBox.y < bannerBox.y + bannerBox.height &&
        inputBox.y + inputBox.height > bannerBox.y;
      const overlapX =
        inputBox.x < bannerBox.x + bannerBox.width &&
        inputBox.x + inputBox.width > bannerBox.x;
      expect(
        overlapX && overlapY,
        "banner must not overlap the search input",
      ).toBeFalsy();
    }
    await input.fill("EH1");
    await expect(input).toHaveValue("EH1");
  });

  test("map (i) attribution includes Royal Mail, ONS and endorsement", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator(".maplibregl-ctrl-attrib").waitFor();
    await openAttributionIfCollapsed(page);
    const attrib = page.locator(".maplibregl-ctrl-attrib");
    await expect(attrib).toContainText("Royal Mail");
    await expect(attrib).toContainText("Office for National Statistics");
    await expect(attrib).toContainText("No data provider endorses this site");
    // One-line footer unchanged.
    await expect(page.getByTestId("map-footer-line")).toHaveText(
      "Research estimate · Open data · Sources and licences",
    );
  });
});

test.describe("site-watch PR A — chrome nits", () => {
  test("390x844 footer + collapsed attribution ≤ ~10% height", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator(".maplibregl-ctrl-attrib").waitFor();
    const footer = page.getByTestId("map-stamp-footer");
    const attrib = page.locator(".maplibregl-ctrl-attrib");
    await expect(footer).toBeVisible();
    await expect(attrib).toBeVisible();
    // Prefer collapsed (i) control; collapse without fighting overlay clicks.
    await attrib.evaluate((el) => {
      el.classList.remove("maplibregl-compact-show");
      const details = el as HTMLDetailsElement;
      if ("open" in details) details.open = false;
    });
    const footerBox = await footer.boundingBox();
    const attribBox = await attrib.boundingBox();
    expect(footerBox && attribBox).toBeTruthy();
    if (footerBox && attribBox) {
      const used = footerBox.height + attribBox.height;
      expect(used).toBeLessThanOrEqual(844 * 0.1 + 8);
    }
  });

  test("Layers button sits top-right at 1280", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const layers = page.getByTestId("hud-layers-btn");
    const brand = page.locator(".hud-brand");
    await expect(layers).toBeVisible();
    const layersBox = await layers.boundingBox();
    const brandBox = await brand.boundingBox();
    expect(layersBox && brandBox).toBeTruthy();
    if (layersBox && brandBox) {
      expect(layersBox.x).toBeGreaterThan(brandBox.x + brandBox.width);
      expect(layersBox.x + layersBox.width).toBeGreaterThan(1280 * 0.7);
      expect(layersBox.y).toBeLessThan(120);
    }
  });
});
