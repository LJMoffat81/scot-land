/**
 * YET-WORDING-1: in-scope visitor copy carries no "yet" / "later".
 * Covers the shared research banner, the /methodology banner and the three
 * place-card strings (pill, pre-amount line, scope note). Exact texts are
 * pinned in the existing tests; this file only adds the negative check.
 */
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  openPlaceViaCoords,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import {
  METHODOLOGY_RESEARCH_BANNER_BODY,
  METHODOLOGY_RESEARCH_BANNER_TEXT,
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_TEXT,
} from "../../lib/siteNav";
import {
  PLACE_CARD_AGR_SCOPE_NOTE,
  PLACE_CARD_FIGURE_STATUS,
  PLACE_CARD_PRE_POUND,
} from "../../lib/placeCard";

registerOpenFreeMapFontStub();

const YET_LATER = /\byet\b|\blater\b/i;

test.describe("YET-WORDING-1 no yet / later", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Y1 in-scope constants", () => {
    const strings = {
      RESEARCH_BANNER_BODY,
      RESEARCH_BANNER_TEXT,
      METHODOLOGY_RESEARCH_BANNER_BODY,
      METHODOLOGY_RESEARCH_BANNER_TEXT,
      PLACE_CARD_FIGURE_STATUS,
      PLACE_CARD_PRE_POUND,
      PLACE_CARD_AGR_SCOPE_NOTE,
    };
    for (const [name, text] of Object.entries(strings)) {
      expect(text, name).not.toMatch(YET_LATER);
    }
  });

  test("Y2 rendered banners on /about and /methodology", async ({ page, gate }) => {
    test.setTimeout(90_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    for (const path of ["/about", "/methodology"]) {
      await page.goto(path);
      const banner = page.getByTestId("research-banner");
      await expect(banner).toHaveCount(1);
      await expect(banner).toContainText("Research estimate.");
      expect(await banner.innerText(), path).not.toMatch(YET_LATER);
    }
    assertConsoleClean(gate);
  });

  test("Y3 rendered place-card pill, pre-amount line and scope note", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page, { gbpLive: false });
    await openPlaceViaCoords(page);
    const ids = [
      "place-card-figure-status",
      "place-card-figure",
      "place-card-agr-scope",
    ];
    for (const id of ids) {
      const el = page.getByTestId(id);
      await expect(el).toBeVisible();
      expect(await el.innerText(), id).not.toMatch(YET_LATER);
    }
    assertConsoleClean(gate);
  });
});
