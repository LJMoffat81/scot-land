import { expect, test, type Page } from "@playwright/test";

/**
 * SW-030 — sea / out-of-area stub:
 * the round × close button must not overlap the sea-line text
 * (was clipping the "p" of "Tap" on the first line).
 * Viewports: 1280×800 and 390×844. Console / pageerror fail the test.
 */

/** MAP-CARDS §5.2 — exact sea / outside-Scotland line. */
const OUT_OF_SCOTLAND_LINE = "We only cover land in Scotland.";

/** SW-019 sample: west of the public bounds check (lng < -8.5). */
const OUTSIDE_LAT = 59.66616;
const OUTSIDE_LNG = -9.196485;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const OUTSIDE_DETAIL = "Coordinates appear to be outside Scotland.";

type ConsoleGate = {
  consoleErrors: string[];
  resourceFails: Array<{ url: string; status: number }>;
};

type Box = { x: number; y: number; width: number; height: number };

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const resourceFails: Array<{ url: string; status: number }> = [];
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
    if (status === 404 || status === 400 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
  });
  return { consoleErrors, resourceFails };
}

function assertConsoleClean(gate: ConsoleGate) {
  const unexpectedResourceFails = gate.resourceFails.filter((fail) => {
    if (
      (fail.status === 404 || fail.status === 400) &&
      /data-zones\/at|platform\/place|api\/place\.json/i.test(fail.url)
    ) {
      return false;
    }
    return true;
  });
  expect(
    unexpectedResourceFails,
    `unexpected HTTP 400/404/503:\n${unexpectedResourceFails
      .map((f) => `${f.status} ${f.url}`)
      .join("\n")}`,
  ).toEqual([]);

  const meaningful = gate.consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (400|404|503)/i.test(
        text,
      )
    ) {
      if (!/https?:\/\//i.test(text) && unexpectedResourceFails.length === 0) {
        return false;
      }
      return true;
    }
    return true;
  });
  expect(
    meaningful,
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
}

async function stubMapChrome(page: Page) {
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
}

async function stubSeaMissPlaceApis(page: Page) {
  await page.route("**/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  });
  await page.route("**/platform/place**", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  });
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  });
}

function boxesOverlap(a: Box, b: Box) {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function openSeaStub(page: Page) {
  // Prefer deep-link boot (avoids search chrome races in CI).
  await page.goto(`/?lat=${OUTSIDE_LAT}&lng=${OUTSIDE_LNG}`);
  await page.locator(".maplibregl-canvas").waitFor();

  const line = page.getByTestId("place-card-out-of-scotland");
  if ((await line.count()) === 0) {
    await page.locator("#place-query").waitFor();
    await page.locator("#place-query").fill(`${OUTSIDE_LAT}, ${OUTSIDE_LNG}`);
    await page.locator(".hud-search-go").click();
  }

  await expect(line).toBeVisible({ timeout: 30_000 });
  await expect(line).toHaveText(OUT_OF_SCOTLAND_LINE);

  // Wait out the loading→sea-miss re-render so the line stays mounted
  // (detached nodes yield empty computed padding → NaN).
  await expect(page.getByTestId("place-card-loading")).toHaveCount(0);
  await expect(line).toBeVisible();
  await expect(line).toHaveText(OUT_OF_SCOTLAND_LINE);

  const text = page.getByTestId("place-card-sea-line-text");
  await expect(text).toBeVisible();

  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveClass(/place-card-sea-miss/);
  return { card, line, text };
}

async function assertCloseClearsSeaLineText(page: Page) {
  const gate = attachConsoleGate(page);
  await stubMapChrome(page);
  await stubSeaMissPlaceApis(page);

  await openSeaStub(page);

  // Re-query inside toPass — remounts detach prior handles (scrollIntoView
  // threw "not attached"). Asserts stay strict: pad ≥ ×width+8, no overlap.
  await expect(async () => {
    const line = page.getByTestId("place-card-out-of-scotland");
    const text = page.getByTestId("place-card-sea-line-text");
    const close = page.getByRole("button", { name: "Close place card" });
    await expect(page.getByTestId("place-card-loading")).toHaveCount(0);
    await expect(close).toBeVisible();
    await expect(line).toBeVisible();
    await expect(text).toBeVisible();

    const closeBox = await close.boundingBox();
    expect(closeBox, "close × bounding box").toBeTruthy();

    const padRight = await line.evaluate((el) => {
      if (!el.isConnected) return Number.NaN;
      return parseFloat(getComputedStyle(el).paddingRight);
    });
    expect(Number.isFinite(padRight), "sea-line padding-right finite").toBe(
      true,
    );
    expect(
      padRight,
      `sea-line padding-right ${padRight} < × width ${closeBox!.width} + 8`,
    ).toBeGreaterThanOrEqual(closeBox!.width + 8);

    const textBox = await text.boundingBox();
    expect(textBox, "sea-line text bounding box").toBeTruthy();

    expect(
      boxesOverlap(closeBox!, textBox!),
      `× overlaps sea-line text: close=${JSON.stringify(closeBox)} text=${JSON.stringify(textBox)}`,
    ).toBe(false);
  }).toPass({ timeout: 15_000 });

  assertConsoleClean(gate);
}

test.describe("SW-030 sea close padding 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("× and sea-line text bounding boxes do not overlap", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await assertCloseClearsSeaLineText(page);
  });
});

test.describe("SW-030 sea close padding 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("× and sea-line text bounding boxes do not overlap", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await assertCloseClearsSeaLineText(page);
  });
});
