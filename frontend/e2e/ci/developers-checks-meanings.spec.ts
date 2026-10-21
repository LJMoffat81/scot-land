import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";

import { CHECK_MEANINGS, type CheckMeaningId } from "../../lib/checkMeanings";

registerOpenFreeMapFontStub();


/**
 * /developers/checks — public “what the checks mean” lines (class check-meaning).
 * Stub ledger.json + health (developers layout footer); fail on console / pageerror.
 */

/** Exact order must match LEDGER_CHECK_ORDER (locked by test:check-meanings). */
const CHECK_ORDER = Object.keys(CHECK_MEANINGS) as CheckMeaningId[];

const EXACT_MEANINGS = [
  "Each hectare is counted once.",
  "Wind turbine sites are counted once and only where they stand.",
  "Fish farm sites are counted once and only at sea.",
  "Mineral sites are counted once.",
  "Woodland is counted once.",
  "Planning allocations change best use but add no value on their own.",
  "Limits on use change best use and add no value.",
  "Where layers overlap, the land is not counted twice.",
  "Totals are added up per label only, never across labels or price years.",
  "The yield used stays inside its agreed cap.",
] as const;

function stubChecks() {
  return CHECK_ORDER.map((id, i) => ({
    id,
    meaning: `stub API meaning ${id}`,
    result: "pass" as const,
    run_hash: `e2e-run-${id}-${i}`,
    test_log: [
      {
        id: `stub_${id}`,
        status: "pass",
        detail: "e2e stub log entry",
      },
    ],
  }));
}

const LEDGER_STUB = {
  version: 1,
  kind: "agr_breakdown_catalog",
  brief: "e2e stub — not live rents",
  checks: stubChecks(),
  excluded: [],
  benchmarks: [],
  benchmark_label: "e2e",
  published: false,
};

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

test.describe("/developers/checks meanings", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("shows all 10 exact check-meaning lines", async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });

    // ContentPageFooter (developers layout) probes /backend/health.
    await page.route("**/backend/health**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
    });

    await page.route("**/api/ledger.json**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(LEDGER_STUB),
      });
    });

    await page.goto("/developers/checks");
    await expect(page.getByTestId("developers-checks-page")).toBeVisible();
    await expect(page.getByTestId("developers-checks-table")).toBeVisible();

    const meanings = page.locator("span.check-meaning");
    await expect(meanings).toHaveCount(10);

    expect(CHECK_ORDER).toEqual([
      "C-hectare",
      "C-turbine",
      "C-aqua",
      "C-mineral",
      "C-forest",
      "C-planning",
      "C-overlay",
      "C-overlap",
      "C-totals",
      "C-cap",
    ]);

    for (let i = 0; i < CHECK_ORDER.length; i += 1) {
      const id = CHECK_ORDER[i];
      const expected = EXACT_MEANINGS[i];
      expect(CHECK_MEANINGS[id]).toBe(expected);

      const row = page.locator(`tr[data-check-id="${id}"]`);
      await expect(row).toBeVisible();
      await expect(row.locator("span.check-meaning")).toHaveText(expected);
    }

    const texts = await meanings.allTextContents();
    expect(texts.map((t) => t.trim())).toEqual([...EXACT_MEANINGS]);

    expect(
      consoleErrors,
      `console errors on /developers/checks:\n${consoleErrors.join("\n")}`,
    ).toEqual([]);
  });
});
