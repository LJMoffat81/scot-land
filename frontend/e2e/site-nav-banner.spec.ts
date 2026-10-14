import { expect, test } from "@playwright/test";

const ROUTES: Array<{ path: string; current: string }> = [
  { path: "/", current: "Map" },
  { path: "/about", current: "About" },
  { path: "/methodology", current: "How it works" },
  { path: "/data", current: "Data & sources" },
  { path: "/developers", current: "Downloads & API" },
];

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
      if (width <= 1366) {
        // SW-010: search sits on a second row below the nav links.
        const searchBox = await page.locator(".hud-search-dock").boundingBox();
        const aboutBox = await nav
          .getByRole("link", { name: "About", exact: true })
          .boundingBox();
        expect(searchBox && aboutBox).toBeTruthy();
        if (searchBox && aboutBox) {
          expect(searchBox.y).toBeGreaterThan(aboutBox.y + aboutBox.height - 4);
        }
      }
    });
  }
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
});
