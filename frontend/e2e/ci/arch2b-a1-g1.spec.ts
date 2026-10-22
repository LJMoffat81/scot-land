/**
 * ARCH-2b-r3a A1 / G1 — shared empty-manifest fixture must not serve tiles.
 */
import { stubMapCardsBackend } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";

test.describe("ARCH-2b-r3a A1 gate", () => {
  test("G1 shared fixture must not serve tiles", async ({ page, gate }) => {
    test.setTimeout(60_000);
    const tilePath =
      "/backend/v1/tiles/dz2022/2026-10-22.d28ecc72/5/15/9.mvt";
    gate.expectError({ urlPath: tilePath, status: 503, count: 1 });
    await stubMapCardsBackend(page);
    await page.goto("/");
    const status = await page.evaluate(async (path) => {
      const r = await fetch(path);
      return r.status;
    }, tilePath);
    expect(status, "G1: shared fixture must not serve tiles").not.toBe(200);
    expect(status).toBe(503);
  });
});
