import { expect, test, type Locator, type Page } from "@playwright/test";

const GLASGOW = { lng: -4.2514, lat: 55.8609 };

const VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
] as const;

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("map credit and zoom-out stay visible", async ({ page }) => {
      test.setTimeout(60_000);
      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor();
      await page.locator(".maplibregl-ctrl-attrib").waitFor();
      await page.locator(".maplibregl-ctrl-zoom-out").waitFor();
      await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText(
        "OpenFreeMap",
        { timeout: 30_000 },
      );

      await panToGlasgow(page);

      const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
      const attrib = page.locator(".maplibregl-ctrl-attrib");
      for (let step = 0; step < 12; step += 1) {
        const ready = await attrib.textContent();
        if (ready?.includes("Registers of Scotland")) break;
        await zoomIn.click({ timeout: 10_000 });
        await page.waitForTimeout(600);
      }

      await expect(attrib).toContainText("Registers of Scotland", {
        timeout: 20_000,
      });
      await openAttributionIfCollapsed(page);

      const credit = attrib
        .locator(".maplibregl-ctrl-attrib-inner")
        .filter({ hasText: "Registers of Scotland" });
      await assertUncovered(credit, "Registers of Scotland credit");
      await assertUncovered(
        page.locator(".maplibregl-ctrl-zoom-out"),
        "zoom-out button",
      );
    });
  });
}

function mercator(lng: number, lat: number, zoom: number) {
  const scale = 512 * 2 ** zoom;
  const x = ((lng + 180) / 360) * scale;
  const sin = Math.sin((lat * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale;
  return { x, y };
}

async function panToGlasgow(page: Page) {
  await page.locator("#map[data-framed='1']").waitFor({ timeout: 20_000 });
  const cam = await page.locator("#map").evaluate((el) => ({
    lng: Number((el as HTMLElement).dataset.lng),
    lat: Number((el as HTMLElement).dataset.lat),
    zoom: Number((el as HTMLElement).dataset.zoom),
  }));
  const from = mercator(cam.lng, cam.lat, cam.zoom);
  const to = mercator(GLASGOW.lng, GLASGOW.lat, cam.zoom);
  const dx = from.x - to.x;
  const dy = from.y - to.y;
  const start = await page.evaluate(() => {
    const canvas = document.querySelector(".maplibregl-canvas");
    if (!canvas) return null;
    const width = window.innerWidth;
    const height = window.innerHeight;
    for (let y = Math.floor(height * 0.42); y <= Math.floor(height * 0.72); y += 16) {
      for (let x = Math.floor(width * 0.4); x <= Math.floor(width * 0.82); x += 16) {
        if (document.elementFromPoint(x, y) === canvas) return { x, y };
      }
    }
    return null;
  });
  if (!start) throw new Error("No clear canvas point to pan the map to Glasgow");
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + dx, start.y + dy, { steps: 24 });
  await page.waitForTimeout(250);
  await page.mouse.up();
  await page.waitForTimeout(400);
}

async function openAttributionIfCollapsed(page: Page) {
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  const collapsed = await attrib.evaluate((el) => {
    const compact = el.classList.contains("maplibregl-compact");
    const shown = el.classList.contains("maplibregl-compact-show");
    const inner = el.querySelector(".maplibregl-ctrl-attrib-inner");
    if (!inner) return false;
    const style = getComputedStyle(inner);
    const hidden = style.display === "none" || style.visibility === "hidden";
    return (compact && !shown) || hidden;
  });
  if (!collapsed) return;
  await page.locator(".maplibregl-ctrl-attrib-button").click({ timeout: 10_000 });
}

async function assertUncovered(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    const points = [
      { x: box.left + box.width / 2, y: box.top + box.height / 2 },
      { x: box.left + 2, y: box.top + 2 },
      { x: box.right - 2, y: box.top + 2 },
      { x: box.left + 2, y: box.bottom - 2 },
      { x: box.right - 2, y: box.bottom - 2 },
    ];
    const describe = (node: Element) => {
      const id = node.id ? `#${node.id}` : "";
      const cls = (node.getAttribute("class") || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((name) => `.${name}`)
        .join("");
      return `${node.tagName.toLowerCase()}${id}${cls}`;
    };
    const covers: string[] = [];
    for (const point of points) {
      const hit = document.elementFromPoint(point.x, point.y);
      if (!hit || !el.contains(hit)) {
        const name = hit ? describe(hit) : "nothing";
        covers.push(
          `${name} at (${point.x.toFixed(1)}, ${point.y.toFixed(1)})`,
        );
      }
    }
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
      covers,
    };
  });

  expect(result.visibility, label).not.toBe("hidden");
  expect(result.opacity, label).toBeGreaterThan(0);
  expect(result.display, label).not.toBe("none");
  expect(result.width, `${label} has no area`).toBeGreaterThan(0);
  expect(result.height, `${label} has no area`).toBeGreaterThan(0);
  expect(result.left, `${label} is outside the viewport`).toBeGreaterThanOrEqual(0);
  expect(result.top, `${label} is outside the viewport`).toBeGreaterThanOrEqual(0);
  expect(result.right, `${label} is outside the viewport`).toBeLessThanOrEqual(
    result.innerWidth,
  );
  expect(result.bottom, `${label} is outside the viewport`).toBeLessThanOrEqual(
    result.innerHeight,
  );
  expect(
    result.covers,
    `${label} is covered by ${result.covers.join("; ")}`,
  ).toEqual([]);
}
