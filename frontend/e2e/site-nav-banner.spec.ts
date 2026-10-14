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
