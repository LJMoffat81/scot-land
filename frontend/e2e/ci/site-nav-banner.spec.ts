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
/** 404/503 responses seen this test — used to scope console ignores by URL. */
const resourceFails: Array<{ url: string; status: number }> = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

/** Optional static assets whose 404/503 may be ignored (must match URL). */
const KNOWN_OPTIONAL_FAIL_URL = [
  /\/favicon\.ico(?:\?|$)/i,
  /\/apple-touch-icon/i,
];

function isKnownOptionalFailUrl(url: string): boolean {
  return KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(url));
}

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  resourceFails.length = 0;
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

  // Catch-all first (Playwright is LIFO — later routes win).
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
    });
  });

  // Explicit stubs for routes the chrome suite needs without a live API.
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });

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
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: null,
        name: null,
        vintage: null,
      }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.95,
        lng: -3.19,
        place_label: null,
        agr_rows: [],
        constraints: [],
        layers: [],
        links: [],
      }),
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
});

test.afterEach(() => {
  const unknownResourceFails = resourceFails.filter(
    (fail) => !isKnownOptionalFailUrl(fail.url),
  );
  expect(
    unknownResourceFails,
    `unexpected HTTP 404/503:\n${unknownResourceFails
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
      // Ignore only for known optional URLs (message text), or Chromium's
      // URL-less resource line when every recorded 404/503 was optional.
      if (KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(text))) return false;
      if (!/https?:\/\//i.test(text) && unknownResourceFails.length === 0) {
        return false;
      }
      return true;
    }
    return true;
  });
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
        // UX-00: search shares the top-bar row — must not cover nav links.
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
      // Nav link must remain hit-targets (elementFromPoint at link centre).
      const howBox = await nav
        .getByRole("link", { name: "How it works", exact: true })
        .boundingBox();
      expect(howBox).toBeTruthy();
      if (howBox) {
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
    });
  }
});

test.describe("site-watch PR A — SW-013 downloads moved note", () => {
  test("/developers?moved=1#downloads shows note in viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/developers?moved=1#downloads");
    const note = page.getByTestId("developers-moved-note");
    await expect(note).toHaveText("Downloads has moved here.");
    await expect(note).toBeInViewport();
    // Hash target is the downloads section; note must live inside it.
    await expect(
      page.getByTestId("developers-downloads").getByTestId("developers-moved-note"),
    ).toHaveCount(1);
    await expect(page.getByTestId("developers-api-moved-note")).toHaveCount(0);
  });

  test("/downloads redirect shows visible moved note", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/downloads");
    await expect(page).toHaveURL(/\/developers\?moved=1/);
    const note = page.getByTestId("developers-moved-note");
    await expect(note).toHaveText("Downloads has moved here.");
    await expect(note).toBeInViewport();
    await expect(page.getByTestId("developers-api-moved-note")).toHaveCount(0);
  });

  test("/developers without moved=1 hides the note", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/developers");
    await expect(page.getByTestId("developers-moved-note")).toHaveCount(0);
    await expect(page.getByTestId("developers-api-moved-note")).toHaveCount(0);
  });

  test("/developers?moved=1#api shows API note in viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/developers?moved=1#api");
    const note = page.getByTestId("developers-api-moved-note");
    await expect(note).toHaveText("The API page has moved here.");
    await expect(note).toBeInViewport();
    await expect(
      page.getByTestId("developers-api").getByTestId("developers-api-moved-note"),
    ).toHaveCount(1);
    await expect(page.getByTestId("developers-moved-note")).toHaveCount(0);
  });

  test("/open-api redirect shows API moved note", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 });
    await page.goto("/open-api");
    await expect(page).toHaveURL(/\/developers\?moved=1/);
    await expect(page).toHaveURL(/#api/);
    const note = page.getByTestId("developers-api-moved-note");
    await expect(note).toHaveText("The API page has moved here.");
    await expect(note).toBeInViewport();
    await expect(page.getByTestId("developers-moved-note")).toHaveCount(0);
  });

  test("/open-api redirect shows API moved note at 390x844", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/open-api");
    await expect(page).toHaveURL(/\/developers\?moved=1/);
    await expect(page).toHaveURL(/#api/);
    const note = page.getByTestId("developers-api-moved-note");
    await expect(note).toHaveText("The API page has moved here.");
    await expect(note).toBeInViewport();
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
    await page.route("**/layers/context/data-zones/at**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01008677",
          name: "Old Town",
          vintage: 2022,
        }),
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
    // Keep the research banner: SW-014 asserts suggest stacks above it (do not dismiss).
    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });

    const input = page.locator("#place-query");
    await input.fill("EH1 1YZ");
    // Wait for debounce (250ms) + suggest response.
    const first = page.locator("#place-suggestions button").first();
    await expect(first).toBeVisible({ timeout: 20_000 });
    await expect(first).toContainText(/EH1/i);

    // Suggestion must sit above the research banner (clickable).
    const suggestBox = await first.boundingBox();
    const bannerBox = await banner.boundingBox();
    expect(suggestBox).toBeTruthy();
    expect(bannerBox).toBeTruthy();
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
    const placeCard = page.getByTestId("place-card");
    await expect(placeCard).toBeVisible({ timeout: 30_000 });
    // Intro collapses while the card is open.
    await expect(page.locator(".app-shell")).toHaveClass(/place-open/);
    await expect(page.locator(".hud-scotland-job")).toBeHidden();

    // Root-cause check: spinner must clear after suggest pick (not masked).
    await expect(page.locator(".hud-search.loading")).toHaveCount(0, {
      timeout: 10_000,
    });

    // Item 12: restore Find a place intro when the card closes.
    const close = placeCard.getByRole("button", { name: "Close place card" });
    await expect(close).toBeVisible();
    await close.click();
    await expect(placeCard).toHaveCount(0);
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
    await expect(page.getByTestId("research-banner")).toHaveCount(1);
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
    const attrib = page.locator(".maplibregl-ctrl-attrib");
    await attrib.waitFor({ state: "attached" });
    // App collapses MapLibre's initial compact-show; <details> without open
    // is not "visible" to Playwright — assert class + (i) button instead.
    await expect(attrib).toHaveClass(/maplibregl-compact/);
    await expect(attrib).not.toHaveClass(/maplibregl-compact-show/);
    const attribButton = page.locator(".maplibregl-ctrl-attrib-button");
    await expect(attribButton).toBeVisible();
    const footer = page.getByTestId("map-stamp-footer");
    await expect(footer).toBeVisible();
    const footerBox = await footer.boundingBox();
    const attribBox = await attribButton.boundingBox();
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
