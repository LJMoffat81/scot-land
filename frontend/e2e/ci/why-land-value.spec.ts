import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * STORY-1 — /why-land-value at 1280 and 390.
 * Disclaimer, footer and About links, no digits, no £, no banned words.
 */

const DISCLAIMER =
  "This page explains an idea. It is not a policy promise, and it is not the position of any political party.";

const BANNED = [
  /natural capital/i,
  /\bledger\b/i,
  /\bheadline\b/i,
  /\bshadow\b/i,
  /\byield\b/i,
  /what3words/i,
  /\bneighbourhood\b/i,
] as const;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "e2e stub" }),
    });
  });
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
});

function assertNoConsoleErrors() {
  const meaningful = consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
}

async function assertNoOverflow(page: Page) {
  const fits = await page.evaluate(
    () =>
      (document.scrollingElement ?? document.documentElement).scrollWidth <=
      window.innerWidth,
  );
  expect(fits).toBe(true);
}

async function assertStoryCopy(page: Page) {
  await expect(page).toHaveTitle("Why land value?");
  await expect(
    page.getByRole("heading", { name: "Why land value?", exact: true }),
  ).toBeVisible();
  const copy = page.getByTestId("why-land-value-copy");
  await expect(copy).toContainText(DISCLAIMER);
  await expect(copy.getByRole("link", { name: "map", exact: true })).toHaveAttribute(
    "href",
    "/",
  );
  await expect(
    copy.getByRole("link", { name: "roadmap", exact: true }),
  ).toHaveAttribute("href", "/roadmap");

  const text = await copy.innerText();
  expect(text).not.toMatch(/\d/);
  expect(text).not.toContain("£");
  for (const pattern of BANNED) {
    expect(text).not.toMatch(pattern);
  }
  assertNoConsoleErrors();
}

for (const width of [1280, 390] as const) {
  test.describe(`STORY-1 at ${width}px`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 800 } });

    test("page loads with the disclaimer and clean copy", async ({ page }) => {
      await page.goto("/why-land-value");
      await assertStoryCopy(page);
      await assertNoOverflow(page);
    });

    test("footer link opens the page", async ({ page }) => {
      await page.goto("/about");
      await page
        .getByTestId("content-page-footer")
        .getByRole("link", { name: "Why land value?", exact: true })
        .click();
      await expect(page).toHaveURL(/\/why-land-value$/);
      await assertStoryCopy(page);
      await assertNoOverflow(page);
    });

    test("/about link opens the page", async ({ page }) => {
      await page.goto("/about");
      await page
        .getByTestId("mission-page")
        .locator("p.meta + p")
        .getByRole("link", { name: "Why land value?", exact: true })
        .click();
      await expect(page).toHaveURL(/\/why-land-value$/);
      await assertStoryCopy(page);
      await assertNoOverflow(page);
    });
  });
}
