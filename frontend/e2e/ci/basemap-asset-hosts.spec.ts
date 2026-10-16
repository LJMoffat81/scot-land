import { expect, test, type Page } from "@playwright/test";

/**
 * Production build (`next build && next start`).
 * Whatever host the map already uses, a loaded style, tile, sprite or glyph
 * URL must not be an internal host: a bare hex hostname, localhost, or :3000.
 */

function expandTemplate(raw: string): URL {
  return new URL(raw.replace(/\{[^{}]+\}/g, "0"));
}

function assertNoInternalHost(raw: string) {
  expect(raw, raw).not.toMatch(/:3000\b/);
  const url = expandTemplate(raw);
  expect(url.hostname, raw).not.toMatch(/localhost|127\.0\.0\.1/i);
  expect(url.hostname, raw).not.toMatch(/^[0-9a-f]{6,}$/i);
  expect(url.port, raw).not.toBe("3000");
}

function isMapAssetUrl(raw: string): boolean {
  let url: URL;
  try {
    url = expandTemplate(raw);
  } catch {
    return false;
  }
  const path = url.pathname;
  if (/\/styles\/(positron|liberty)\b/i.test(path)) return true;
  if (/\/sprites\//i.test(path)) return true;
  if (/\/fonts\//i.test(path) && /\.pbf$/i.test(path)) return true;
  if (/\/planet\b/i.test(path)) return true;
  if (/\.pbf$/i.test(path)) return true;
  if (/\/api\/ofm\b/i.test(path)) return true;
  return false;
}

function urlsInStyle(style: {
  sprite?: unknown;
  glyphs?: unknown;
  sources?: Record<string, { url?: unknown; tiles?: unknown }>;
}): string[] {
  const urls: string[] = [];
  if (typeof style.sprite === "string") urls.push(style.sprite);
  if (typeof style.glyphs === "string") urls.push(style.glyphs);
  for (const source of Object.values(style.sources ?? {})) {
    if (typeof source.url === "string") urls.push(source.url);
    if (Array.isArray(source.tiles)) {
      for (const tile of source.tiles) {
        if (typeof tile === "string") urls.push(tile);
      }
    }
  }
  return urls;
}

async function quietAppApis(page: Page) {
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "FeatureCollection", features: [] }),
    });
  });
}

test("loaded style, tile, sprite and glyph URLs have no internal host", async ({
  page,
}) => {
  test.setTimeout(90_000);
  const requested: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (isMapAssetUrl(url)) requested.push(url);
  });

  await quietAppApis(page);

  const lightStyle = page.waitForResponse(
    (response) =>
      /\/styles\/positron(?:\?|$)/i.test(response.url()) && response.ok(),
  );

  await page.goto("/", { waitUntil: "domcontentloaded" });
  const light = await lightStyle;
  expect(light.url()).toMatch(/[?&]v=/);
  const lightUrls = [light.url(), ...urlsInStyle(await light.json())];
  expect(lightUrls.length).toBeGreaterThan(1);
  for (const url of lightUrls) assertNoInternalHost(url);

  const planet = await page.waitForResponse(
    (response) =>
      /\/planet(?:\?|$)/i.test(response.url()) &&
      !/\.pbf(?:\?|$)/i.test(response.url()) &&
      response.ok(),
    { timeout: 30_000 },
  );
  const planetBody = (await planet.json()) as { tiles?: unknown };
  expect(Array.isArray(planetBody.tiles)).toBe(true);
  const planetTiles = (planetBody.tiles as unknown[]).filter(
    (tile): tile is string => typeof tile === "string",
  );
  expect(planetTiles.length).toBeGreaterThan(0);
  for (const url of [planet.url(), ...planetTiles]) assertNoInternalHost(url);

  await expect
    .poll(() => requested.some((url) => /\/sprites\//i.test(url)))
    .toBe(true);
  await expect
    .poll(() =>
      requested.some((url) => /\/fonts\//i.test(url) && /\.pbf/i.test(url)),
    )
    .toBe(true);

  await page.getByTestId("basemap-switcher").click();
  const liberty = await page.waitForResponse(
    (response) =>
      /\/styles\/liberty(?:\?|$)/i.test(response.url()) && response.ok(),
    { timeout: 30_000 },
  );
  expect(liberty.url()).toMatch(/[?&]v=/);
  const libertyUrls = [liberty.url(), ...urlsInStyle(await liberty.json())];
  expect(libertyUrls.length).toBeGreaterThan(1);
  for (const url of libertyUrls) assertNoInternalHost(url);

  const loaded = await page.evaluate(() => {
    const map = (
      window as unknown as {
        __SCOT_LAND_MAP__?: {
          getStyle?: () => {
            sprite?: string;
            glyphs?: string;
            sources?: Record<string, { url?: string; tiles?: string[] }>;
          };
        };
      }
    ).__SCOT_LAND_MAP__;
    const style = map?.getStyle?.();
    if (!style) return [];
    const urls: string[] = [];
    if (style.sprite) urls.push(style.sprite);
    if (style.glyphs) urls.push(style.glyphs);
    for (const source of Object.values(style.sources ?? {})) {
      if (source.url) urls.push(source.url);
      if (source.tiles) urls.push(...source.tiles);
    }
    return urls;
  });
  expect(loaded.length).toBeGreaterThan(0);
  for (const url of loaded) assertNoInternalHost(url);

  const sprites = requested.filter((url) => /\/sprites\//i.test(url));
  const glyphs = requested.filter(
    (url) => /\/fonts\//i.test(url) && /\.pbf/i.test(url),
  );
  const tiles = [...planetTiles, ...requested.filter((url) => /\.pbf/i.test(url))];
  expect(sprites.length).toBeGreaterThan(0);
  expect(glyphs.length).toBeGreaterThan(0);
  expect(tiles.length).toBeGreaterThan(0);
  for (const url of [...requested, ...sprites, ...glyphs, ...tiles]) {
    assertNoInternalHost(url);
  }
});
