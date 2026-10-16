import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

import { BANNED_VISIBLE } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();


/**
 * ROADMAP-RURAL-1 — one "Rural and farmland values" row, status Later.
 */

const ROW_NAME = "Rural and farmland values";
const ROW_DESCRIPTION =
  "Homes rarely sell in the countryside, so house-sale methods don't work there. We will use published farmland price and rent surveys, plus land capability (soil) maps.";

const BANNED = [
  /natural capital/i,
  /\bledger\b/i,
  /\bheadline\b/i,
  /\bshadow\b/i,
  /\byield\b/i,
  /what3words/i,
  /\bneighbourhood\b/i,
  BANNED_VISIBLE,
] as const;

async function assertRuralRow(page: Page) {
  await page.goto("/roadmap");
  const named = page.getByText(ROW_NAME, { exact: true });
  await expect(named).toHaveCount(1);

  const row = page.getByTestId("roadmap-aim-row").filter({
    has: page.getByText(ROW_NAME, { exact: true }),
  });
  await expect(row).toHaveCount(1);
  await expect(row).toContainText(ROW_DESCRIPTION);
  await expect(row.getByTestId("roadmap-aim-status")).toHaveText("Later");

  const text = await row.innerText();
  expect(text).not.toMatch(/\d/);
  expect(text).not.toContain("£");
  for (const pattern of BANNED) {
    expect(text).not.toMatch(pattern);
  }

  const body = await page.locator("body").innerText();
  expect(body).not.toContain("£");
  for (const pattern of BANNED) {
    expect(body).not.toMatch(pattern);
  }
}

test.describe("ROADMAP-RURAL-1 at 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("one Rural and farmland values row is Later", async ({ page }) => {
    await assertRuralRow(page);
  });
});

test.describe("ROADMAP-RURAL-1 at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("one Rural and farmland values row is Later", async ({ page }) => {
    await assertRuralRow(page);
  });
});
