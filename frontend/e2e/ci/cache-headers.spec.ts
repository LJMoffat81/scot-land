import { expect, test } from "@playwright/test";

/**
 * HOME-TUNNEL: static assets must advertise a long Cache-Control lifetime.
 * Auto-discovered under e2e/ci/.
 */
test.describe("cache headers (HOME-TUNNEL)", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("static mark image has a long Cache-Control max-age", async ({
    request,
  }) => {
    const res = await request.get("/scot-land-mark.png");
    expect(res.ok()).toBeTruthy();
    const cache = res.headers()["cache-control"] || "";
    expect(cache.toLowerCase()).toMatch(/public/i);
    const match = /max-age=(\d+)/i.exec(cache);
    expect(match).not.toBeNull();
    const maxAge = Number(match![1]);
    // Long lifetime: at least one day (86400). Hashed Next assets may be longer.
    expect(maxAge).toBeGreaterThanOrEqual(86400);
  });
});
