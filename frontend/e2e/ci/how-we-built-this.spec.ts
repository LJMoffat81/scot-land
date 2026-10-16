import { expect, test, type Page } from "@playwright/test";

/**
 * HOW-WE-BUILT-1 — /how-we-built-this at 1280 and 390.
 * Exact visitor copy, nav and About links, no £, no 4-digit year,
 * no banned words. Console errors fail the test.
 */

const ROLE_LINES = [
  "Georgist economics: keeps the work true to land value principles.",
  "Valuation: models land values from sales and building costs.",
  "Econometrics: tests how well the land value model fits the evidence.",
  "Methods and statistics: checks that each method is sound and written down before it is used.",
  "GIS: handles maps, boundaries and how data is joined to areas.",
  "Data scouting: finds public data and checks its licence.",
  "Building costs: estimates what it would cost to rebuild homes, so land can be separated from buildings.",
  "Design: the look of the site and maps.",
  "Wording: keeps every page clear and plain.",
  "Quality checks: tests the live site after every change.",
  "Engineering lead: writes specs and reviews code",
  "Coordination: plans work and checks it against our rules",
  "Outreach: drafts messages, only sent with Laurie's approval",
] as const;

const GAP_LINES = [
  "No qualified valuer has reviewed our method.",
  "Values cover land as it is used today, not what planning might allow.",
  "No legal or data-protection review yet.",
  'No public-finance expert has reviewed our "Why land value?" page.',
  "Rural land is not valued yet.",
  "No independent review of our statistics.",
] as const;

const REVIEWER_LINES = [
  "a RICS-registered valuer, to check how we value land",
  "a statistician, to test our model",
  "a planner, to advise on planning use",
  "a legal or data-protection reviewer",
  "a public-finance economist, to review our tax explainer",
] as const;

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

async function openNavIfMobile(page: Page) {
  const menu = page.getByTestId("site-nav-menu-btn");
  if (await menu.isVisible()) {
    await menu.click();
    await expect(page.getByTestId("site-nav-panel")).toBeVisible();
  }
}

async function assertPageCopy(page: Page) {
  const root = page.getByTestId("how-we-built-page");
  await expect(root).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "How we built this", exact: true }),
  ).toBeVisible();
  const copy = page.getByTestId("how-we-built-copy");
  await expect(copy).toContainText("Scot-LAND is led by Laurie Moffat.");
  expect(ROLE_LINES).toHaveLength(13);
  const roles = copy.getByTestId("how-we-built-roles").getByRole("listitem");
  await expect(roles).toHaveCount(13);
  for (const line of ROLE_LINES) {
    await expect(roles.filter({ hasText: line })).toHaveCount(1);
  }
  await expect(copy).toContainText(
    "These are AI assistants, not people, and they hold no professional qualifications.",
  );
  expect(GAP_LINES).toHaveLength(6);
  const gaps = copy.getByTestId("how-we-built-gaps").getByRole("listitem");
  await expect(gaps).toHaveCount(6);
  for (const line of GAP_LINES) {
    await expect(gaps.filter({ hasText: line })).toHaveCount(1);
  }
  await expect(
    copy.getByRole("heading", { name: "What we don't have yet", exact: true }),
  ).toBeVisible();
  await expect(copy).toContainText(
    "Automated values need human checking before anyone relies on them.",
  );
  await expect(copy).toContainText("We would welcome volunteer reviewers:");
  expect(REVIEWER_LINES).toHaveLength(5);
  const reviewers = copy.getByTestId("how-we-built-reviewers").getByRole("listitem");
  await expect(reviewers).toHaveCount(5);
  for (const line of REVIEWER_LINES) {
    await expect(reviewers.filter({ hasText: line })).toHaveCount(1);
  }
  await expect(copy).toContainText("This is unpaid and voluntary.");
  await expect(copy.getByRole("link", { name: "How it works" })).toHaveAttribute(
    "href",
    "/methodology",
  );
  await expect(copy.getByRole("link", { name: "Data & sources" })).toHaveAttribute(
    "href",
    "/data",
  );
  await expect(copy.getByRole("link", { name: "GitHub project" })).toHaveAttribute(
    "href",
    "https://github.com/LJMoffat81/scot-land",
  );

  const text = await copy.innerText();
  expect(text).not.toContain("£");
  expect(text).not.toMatch(/\b\d{4}\b/);
  for (const pattern of BANNED) {
    expect(text).not.toMatch(pattern);
  }

  const involvedText = await page.locator("#get-involved").innerText();
  const gapsText = await page.locator("#what-we-dont-have-yet").innerText();
  const outside = text.replace(involvedText, "").replace(gapsText, "");
  expect(outside).not.toMatch(/\bqualified\b/i);
  expect(outside).not.toMatch(/\bchartered\b/i);
  expect(outside).not.toMatch(/\bcertified\b/i);
  expect(outside).not.toMatch(/expert team/i);

  const body = await page.locator("body").innerText();
  expect(body).not.toContain("£");
  assertNoConsoleErrors();
}

for (const width of [1280, 390] as const) {
  test.describe(`HOW-WE-BUILT-1 at ${width}px`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 800 } });

    test("page renders the heading, thirteen roles, and the qualifications sentence", async ({
      page,
    }) => {
      await page.goto("/how-we-built-this");
      await assertPageCopy(page);
    });

    test("nav reaches the page", async ({ page }) => {
      await page.goto("/about");
      await openNavIfMobile(page);
      const nav = page.getByTestId("site-nav");
      await nav
        .getByRole("link", { name: "How we built this", exact: true })
        .click();
      await expect(page).toHaveURL(/\/how-we-built-this$/);
      await assertPageCopy(page);
    });

    test("/about link reaches the page", async ({ page }) => {
      await page.goto("/about");
      // The nav also says "How we built this". The About link is the one
      // in the page copy, beside Back to map.
      await page
        .getByTestId("mission-page")
        .locator("p.meta + p")
        .getByRole("link", { name: "How we built this", exact: true })
        .click();
      await expect(page).toHaveURL(/\/how-we-built-this$/);
      await assertPageCopy(page);
    });
  });
}
