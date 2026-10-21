
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, BANNED_VISIBLE, stubMapCardsBackend } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * ROADMAP-VISION-1 — "Our vision" sits on /roadmap at desktop and phone widths.
 * Auto-discovered by playwright.ci.config.ts (its own spec; not a shared list).
 */

const VISION_HEADING = "Our vision";
const VISION_FIRST_SENTENCE =
  "Our long-term aim is to give every piece of land in Scotland its own Annual Ground Rent value, per square metre.";

async function assertVisionVisible(page: Page) {
  await stubMapCardsBackend(page);
  await page.goto("/roadmap");
  const section = page.getByTestId("roadmap-vision");
  const heading = section.getByRole("heading", {
    name: VISION_HEADING,
    exact: true,
  });
  await expect(heading).toBeVisible();
  await expect(section).toContainText(VISION_FIRST_SENTENCE);

  const bodyText = await page.locator("body").innerText();
  expect(bodyText).toContain(VISION_HEADING);
  expect(bodyText).toContain(VISION_FIRST_SENTENCE);
  expect(bodyText).not.toMatch(BANNED_VISIBLE);
}

test.describe("ROADMAP-VISION-1 /roadmap at 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Our vision heading and first sentence are visible", async ({ page }) => {
    await assertVisionVisible(page);
  });
});

test.describe("ROADMAP-VISION-1 /roadmap at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Our vision heading and first sentence are visible", async ({ page }) => {
    await assertVisionVisible(page);
  });
});
