import { expect, test, type Locator } from "@playwright/test";

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
    await assertUnclipped(brand.locator("img"), "brand logo image");
  });

  test("map header has no overlapping or clipped text", async ({ page }) => {
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const brand = page.locator(".hud-brand");
    await expect(brand).toBeVisible();
    await expect(brand.locator(".hud-wordmark img")).toBeVisible();

    const header = page.locator("header.hud-top");
    await assertHeaderTextClear(header, "map hud-top");
    await assertUnclipped(brand.locator(".hud-wordmark img"), "map logo image");
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
    const walk = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) {
        const text = (node.textContent || "").replace(/\s+/g, " ").trim();
        if (!text) return;
        const parent = node.parentElement;
        if (!parent) return;
        const style = getComputedStyle(parent);
        if (
          style.display === "none" ||
          style.visibility === "hidden" ||
          Number(style.opacity) === 0
        ) {
          return;
        }
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
