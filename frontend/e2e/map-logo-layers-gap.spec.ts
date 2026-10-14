import { expect, test, type Page } from "@playwright/test";

/**
 * SW-020 follow-up — at 390px the map logo must not touch Layers, and the
 * mark needs a solid backing so map labels cannot show through the clear
 * header. Load tiles, assert bounding boxes do not overlap, fail on console
 * errors.
 */

const consoleErrors: string[] = [];
const resourceFails: Array<{ url: string; status: number }> = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const KNOWN_OPTIONAL_FAIL_URL = [
  /\/favicon\.ico(?:\?|$)/i,
  /\/apple-touch-icon/i,
];

function isKnownOptionalFailUrl(url: string): boolean {
  return KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(url));
}

function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  const overlapX = a.x < b.x + b.width && a.x + a.width > b.x;
  const overlapY = a.y < b.y + b.height && a.y + a.height > b.y;
  return overlapX && overlapY;
}

test.describe("SW-020 map logo vs Layers gap (390×844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {
    consoleErrors.length = 0;
    resourceFails.length = 0;
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });
    page.on("response", (response) => {
      const status = response.status();
      if (status === 404 || status === 503) {
        resourceFails.push({ url: response.url(), status });
      }
    });

    await page.route("**/backend/**", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
        }),
      });
    });

    await page.route("**/backend/health**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
    });
    await page.route("**/backend/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
    });
    await page.route("**/backend/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
    });
    await page.route("**/backend/layers/open/data-zones**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
    });
    await page.route(
      "**/backend/layers/context/data-zones/at**",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            code: null,
            name: null,
            vintage: null,
          }),
        });
      },
    );
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
    });
  });

  test.afterEach(() => {
    const unknownResourceFails = resourceFails.filter(
      (fail) => !isKnownOptionalFailUrl(fail.url),
    );
    expect(
      unknownResourceFails,
      `unexpected HTTP 404/503:\n${unknownResourceFails
        .map((f) => `${f.status} ${f.url}`)
        .join("\n")}`,
    ).toEqual([]);

    const meaningful = consoleErrors.filter((text) => {
      if (
        /\bAbortError\b|The user aborted|The operation was aborted/i.test(text)
      ) {
        return false;
      }
      if (
        /Failed to load resource: the server responded with a status of (404|503)/i.test(
          text,
        )
      ) {
        if (KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(text))) return false;
        if (!/https?:\/\//i.test(text) && unknownResourceFails.length === 0) {
          return false;
        }
        return true;
      }
      return true;
    });
    expect(
      meaningful,
      `console errors on map logo/Layers e2e:\n${meaningful.join("\n")}`,
    ).toEqual([]);
  });

  test("logo does not overlap Layers after tiles load", async ({ page }) => {
    test.setTimeout(90_000);
    await openMapWithTiles(page);

    const logo = page.locator(".hud-wordmark");
    const layers = page.getByTestId("hud-layers-btn");
    await expect(logo).toBeVisible();
    await expect(layers).toBeVisible();

    // Solid backing — opaque white so map labels cannot show through.
    await expect(logo).toHaveCSS("background-color", "rgb(255, 255, 255)");

    const logoBox = await logo.boundingBox();
    const layersBox = await layers.boundingBox();
    expect(logoBox, "logo bounding box").toBeTruthy();
    expect(layersBox, "Layers bounding box").toBeTruthy();
    if (!logoBox || !layersBox) return;

    expect(
      boxesOverlap(logoBox, layersBox),
      `logo overlaps Layers: logo=${JSON.stringify(logoBox)} layers=${JSON.stringify(layersBox)}`,
    ).toBe(false);

    // Same row: enforce the ≥8px product gap (logo must not touch Layers).
    const sameRow =
      logoBox.y < layersBox.y + layersBox.height &&
      logoBox.y + logoBox.height > layersBox.y;
    if (sameRow) {
      const gap = layersBox.x - (logoBox.x + logoBox.width);
      expect(
        gap,
        `logo→Layers horizontal gap must be ≥8px (got ${gap})`,
      ).toBeGreaterThanOrEqual(8);
    }
  });
});

async function openMapWithTiles(page: Page) {
  const tileResponse = page.waitForResponse(
    (response) => {
      const url = response.url();
      return (
        response.ok() &&
        (/openfreemap\.org/i.test(url) ||
          /\/tiles\//i.test(url) ||
          /\.pbf(?:\?|$)/i.test(url) ||
          /styles\/positron/i.test(url))
      );
    },
    { timeout: 60_000 },
  );

  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await tileResponse;

  await page.waitForFunction(() => {
    const canvas = document.querySelector(
      ".maplibregl-canvas",
    ) as HTMLCanvasElement | null;
    return Boolean(canvas && canvas.width > 0 && canvas.height > 0);
  });
}
