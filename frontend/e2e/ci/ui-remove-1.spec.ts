
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, openMap, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * UI-REMOVE-1 — the centre-identify button and its wording are gone.
 */

const WORDING = "Show the area at map centre";

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`UI-REMOVE-1 (${viewport.width})`, () => {
    test.use({ viewport });

    test("centre identify button is absent", async ({ page }) => {
      test.setTimeout(90_000);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);
      await expect(page.getByTestId("identify-at-centre")).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: WORDING }),
      ).toHaveCount(0);
      await expect(page.getByText(WORDING)).toHaveCount(0);
    });
  });
}
