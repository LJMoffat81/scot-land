import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Locator } from "@playwright/test";

/** Collect console errors / pageerror for every test (data-page.spec.ts pattern). */
const consoleErrors: string[] = [];
/** 404/503 responses seen this test — used to scope console ignores by URL. */
const resourceFails: Array<{ url: string; status: number }> = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

/** Optional static assets whose 404/503 may be ignored (must match URL). */
const KNOWN_OPTIONAL_FAIL_URL = [
  /\/favicon\.ico(?:\?|$)/i,
  /\/apple-touch-icon/i,
];

function isKnownOptionalFailUrl(url: string): boolean {
  return KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(url));
}

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

  // Catch-all first (Playwright is LIFO — later routes win).
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
    });
  });

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
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: null,
        name: null,
        vintage: null,
      }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.95,
        lng: -3.19,
        place_label: null,
        agr_rows: [],
        constraints: [],
        layers: [],
        links: [],
      }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await stubLayersAddQuiet(page);
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
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (404|503)/i.test(
        text,
      )
    ) {
      // Ignore only for known optional URLs (message text), or Chromium's
      // URL-less resource line when every recorded 404/503 was optional.
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
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
});

/**
 * SW-020 — mobile header logo must not overlap or clip wordmark text.
 * At ≤600px the HTML "Scot-LAND" wordmark is hidden; the mark PNG already
 * includes LAND. Assert geometry at the reported 390×844 viewport.
 */
test.describe("SW-020 mobile logo (390×844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("content page brand has no overlapping or clipped header text", async ({
    page,
  }) => {
    await page.goto("/about");
    const brand = page.getByTestId("site-nav-brand");
    await expect(brand).toBeVisible();
    await expect(brand.locator("img")).toBeVisible();
    // Wordmark text is hidden below the mobile breakpoint.
    await expect(brand.locator(".site-nav-wordmark")).toBeHidden();

    const header = page.getByTestId("site-nav");
    await assertHeaderTextClear(header, "content site-nav");
    const logo = brand.locator("img");
    await assertUnclipped(logo, "brand logo image");
    await assertLogoDoesNotCoverText(logo, header, "content brand logo");
  });

  test("map header has no overlapping or clipped text", async ({ page }) => {
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const brand = page.locator(".hud-brand");
    await expect(brand).toBeVisible();
    const logo = brand.locator(".hud-wordmark img");
    await expect(logo).toBeVisible();

    const header = page.locator("header.hud-top");
    await assertHeaderTextClear(header, "map hud-top");
    await assertUnclipped(logo, "map logo image");
    await assertLogoDoesNotCoverText(logo, header, "map logo");
  });
});

test.describe("SW-020 desktop wordmark still shown", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("content page shows Scot-LAND wordmark beside the mark", async ({
    page,
  }) => {
    await page.goto("/about");
    const wordmark = page
      .getByTestId("site-nav-brand")
      .locator(".site-nav-wordmark");
    await expect(wordmark).toBeVisible();
    await expect(wordmark).toHaveText("Scot-LAND");
    await assertUnclipped(wordmark, "desktop wordmark");
  });
});

type Box = { x: number; y: number; width: number; height: number; label: string };

async function assertHeaderTextClear(header: Locator, label: string) {
  const boxes = await header.evaluate((root) => {
    const out: Box[] = [];
    const isVisuallyHidden = (el: Element) => {
      if (el.classList.contains("sr-only")) return true;
      const style = getComputedStyle(el);
      if (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) === 0
      ) {
        return true;
      }
      // Classic sr-only / clip pattern (1px box clipped away).
      if (style.position === "absolute") {
        const clip = style.clip || "";
        const clipPath = style.clipPath || "";
        if (/rect\s*\(/i.test(clip) || clipPath === "inset(50%)") return true;
        if (
          parseFloat(style.width) <= 1 &&
          parseFloat(style.height) <= 1 &&
          (style.overflow === "hidden" || style.overflowX === "hidden")
        ) {
          return true;
        }
      }
      return false;
    };
    const walk = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = (node.textContent || "").replace(/\s+/g, " ").trim();
        if (!text) return;
        const parent = node.parentElement;
        if (!parent || isVisuallyHidden(parent)) return;
        const range = document.createRange();
        range.selectNodeContents(node);
        const rect = range.getBoundingClientRect();
        if (rect.width < 1 || rect.height < 1) return;
        out.push({
          x: rect.left,
          y: rect.top,
          width: rect.width,
          height: rect.height,
          label: text.slice(0, 40),
        });
        return;
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as Element;
        if (el.getAttribute("hidden") !== null) return;
        if (el.getAttribute("aria-hidden") === "true") return;
        if (isVisuallyHidden(el)) return;
        for (const child of Array.from(el.childNodes)) walk(child);
      }
    };
    walk(root);
    return out;
  });

  for (const box of boxes) {
    expect(
      box.x,
      `${label}: "${box.label}" clipped left`,
    ).toBeGreaterThanOrEqual(-0.5);
    expect(
      box.y,
      `${label}: "${box.label}" clipped top`,
    ).toBeGreaterThanOrEqual(-0.5);
    const page = header.page();
    const viewport = page.viewportSize();
    expect(viewport, `${label} viewport`).toBeTruthy();
    if (!viewport) continue;
    expect(
      box.x + box.width,
      `${label}: "${box.label}" clipped right`,
    ).toBeLessThanOrEqual(viewport.width + 0.5);
    expect(
      box.y + box.height,
      `${label}: "${box.label}" clipped bottom`,
    ).toBeLessThanOrEqual(viewport.height + 0.5);
  }

  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      const overlapX =
        a.x < b.x + b.width && a.x + a.width > b.x;
      const overlapY =
        a.y < b.y + b.height && a.y + a.height > b.y;
      expect(
        overlapX && overlapY,
        `${label}: "${a.label}" overlaps "${b.label}"`,
      ).toBe(false);
    }
  }
}

async function assertLogoDoesNotCoverText(
  logo: Locator,
  header: Locator,
  label: string,
) {
  const logoBox = await logo.boundingBox();
  expect(logoBox, `${label} bounding box`).toBeTruthy();
  if (!logoBox) return;

  const textBoxes = await header.evaluate((root) => {
    const out: Box[] = [];
    const skip = (el: Element) => {
      if (el.classList.contains("sr-only")) return true;
      const style = getComputedStyle(el);
      return (
        style.display === "none" ||
        style.visibility === "hidden" ||
        Number(style.opacity) === 0
      );
    };
    const walk = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = (node.textContent || "").replace(/\s+/g, " ").trim();
        if (!text) return;
        const parent = node.parentElement;
        if (!parent || skip(parent)) return;
        const range = document.createRange();
        range.selectNodeContents(node);
        const rect = range.getBoundingClientRect();
        if (rect.width < 1 || rect.height < 1) return;
        out.push({
          x: rect.left,
          y: rect.top,
          width: rect.width,
          height: rect.height,
          label: text.slice(0, 40),
        });
        return;
      }
      if (node.nodeType === Node.ELEMENT_NODE) {
        const el = node as Element;
        if (el.getAttribute("hidden") !== null) return;
        if (el.getAttribute("aria-hidden") === "true") return;
        if (skip(el)) return;
        for (const child of Array.from(el.childNodes)) walk(child);
      }
    };
    walk(root);
    return out;
  });

  for (const text of textBoxes) {
    const overlapX =
      logoBox.x < text.x + text.width && logoBox.x + logoBox.width > text.x;
    const overlapY =
      logoBox.y < text.y + text.height && logoBox.y + logoBox.height > text.y;
    expect(
      overlapX && overlapY,
      `${label} covers header text "${text.label}"`,
    ).toBe(false);
  }
}

async function assertUnclipped(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return {
      visibility: style.visibility,
      opacity: Number(style.opacity),
      display: style.display,
      left: box.left,
      top: box.top,
      right: box.right,
      bottom: box.bottom,
      width: box.width,
      height: box.height,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      scrollHeight: el.scrollHeight,
      clientHeight: el.clientHeight,
    };
  });

  expect(result.visibility, label).not.toBe("hidden");
  expect(result.opacity, label).toBeGreaterThan(0);
  expect(result.display, label).not.toBe("none");
  expect(result.width, `${label} has no area`).toBeGreaterThan(0);
  expect(result.height, `${label} has no area`).toBeGreaterThan(0);
  expect(result.left, `${label} clipped left`).toBeGreaterThanOrEqual(-0.5);
  expect(result.top, `${label} clipped top`).toBeGreaterThanOrEqual(-0.5);
  expect(result.right, `${label} clipped right`).toBeLessThanOrEqual(
    result.innerWidth + 0.5,
  );
  expect(result.bottom, `${label} clipped bottom`).toBeLessThanOrEqual(
    result.innerHeight + 0.5,
  );
  expect(
    result.scrollWidth,
    `${label} text/content overflows horizontally`,
  ).toBeLessThanOrEqual(result.clientWidth + 1);
  expect(
    result.scrollHeight,
    `${label} text/content overflows vertically`,
  ).toBeLessThanOrEqual(result.clientHeight + 1);
}
