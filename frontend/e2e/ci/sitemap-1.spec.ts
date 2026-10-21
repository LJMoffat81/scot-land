import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";

registerOpenFreeMapFontStub();


/**
 * SITEMAP-1 — static sitemap of public content pages, and robots.txt pointing at it.
 * Every listed URL must respond 200. No /api paths.
 */

test("sitemap and robots list public pages that respond", async ({ request }) => {
  const sitemap = await request.get("/sitemap.xml");
  expect(sitemap.status()).toBe(200);
  const xml = await sitemap.text();

  const locs = [...xml.matchAll(/<loc>\s*([^<]+?)\s*<\/loc>/g)].map((match) =>
    match[1].trim(),
  );
  expect(locs.length).toBeGreaterThan(0);

  for (const loc of locs) {
    const url = new URL(loc);
    const path = url.pathname;
    expect(path === "/api" || path.startsWith("/api/"), loc).toBe(false);
    const page = await request.get(path, { maxRedirects: 0 });
    expect(page.status(), path).toBe(200);
  }

  const robots = await request.get("/robots.txt");
  expect(robots.status()).toBe(200);
  const text = await robots.text();
  expect(text).toContain("Sitemap: https://scot-land.scot/sitemap.xml");
});
