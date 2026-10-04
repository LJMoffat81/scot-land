import { expect, test, type Locator, type Page } from "@playwright/test";

const GLASGOW = { lng: -4.2514, lat: 55.8609 };

test.describe("390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("legend toggle is a keyboard button and leaves the credit and zoom clear", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    const toggle = page.locator("button.hud-scotland-fold");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("type", "button");
    await expect(toggle).toHaveAttribute("aria-controls", "hud-scotland-body");

    await reachByTab(page, toggle);
    await assertFocusRing(toggle);
    await expectLegend(page, false);

    await page.keyboard.press("Enter");
    await expect(toggle).toBeFocused();
    await assertFocusRing(toggle);
    await expectLegend(page, true);

    await page.keyboard.press("Enter");
    await expect(toggle).toBeFocused();
    await expectLegend(page, false);

    await page.keyboard.press("Space");
    await expect(toggle).toBeFocused();
    await expectLegend(page, true);

    await page.keyboard.press("Space");
    await expect(toggle).toBeFocused();
    await expectLegend(page, false);

    await revealLongCredit(page);
    await assertCreditAndZoomClear(page);

    await toggle.click();
    await expectLegend(page, true);
    await assertCreditAndZoomClear(page);
  });
});

test.describe("1440x900", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("legend toggle stays hidden and the credit stays uncovered", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    const toggle = page.locator("button.hud-scotland-fold");
    await expect(toggle).toHaveCount(1);
    await expect(toggle).toBeHidden();
    await expect(toggle).toHaveCSS("display", "none");
    await expect(page.locator("#hud-scotland-body")).toBeVisible();

    await revealLongCredit(page);
    const credit = await creditLine(page);
    await assertUncovered(credit, "Registers of Scotland credit");
  });
});

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator(".maplibregl-ctrl-attrib").waitFor();
  await page.locator(".maplibregl-ctrl-zoom-in").waitFor();
  await page.locator(".maplibregl-ctrl-zoom-out").waitFor();
}

async function reachByTab(page: Page, target: Locator) {
  await page.evaluate(() => {
    const active = document.activeElement;
    if (active instanceof HTMLElement) active.blur();
  });
  for (let step = 0; step < 30; step += 1) {
    if (await target.evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  await expect(target).toBeFocused();
}

async function assertFocusRing(locator: Locator) {
  await expect(locator).toBeFocused();
  const ring = await locator.evaluate((el) => {
    const style = getComputedStyle(el);
    return {
      outlineStyle: style.outlineStyle,
      outlineWidth: style.outlineWidth,
      outlineColor: style.outlineColor,
    };
  });
  expect(ring.outlineStyle, JSON.stringify(ring)).not.toBe("none");
  expect(parseFloat(ring.outlineWidth), JSON.stringify(ring)).toBeGreaterThanOrEqual(
    2,
  );
  expect(ring.outlineColor, JSON.stringify(ring)).not.toBe("transparent");
  expect(ring.outlineColor, JSON.stringify(ring)).not.toMatch(
    /rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)/,
  );
}

async function expectLegend(page: Page, open: boolean) {
  const toggle = page.locator("button.hud-scotland-fold");
  const body = page.locator("#hud-scotland-body");
  await expect(toggle).toHaveAttribute("aria-expanded", open ? "true" : "false");
  await expect(toggle).toHaveAttribute("aria-controls", "hud-scotland-body");
  if (open) {
    await expect(toggle).toHaveAccessibleName("Hide legend");
    await expect(toggle.locator(".hud-scotland-fold-hide")).toBeVisible();
    await expect(toggle.locator(".hud-scotland-fold-show")).toBeHidden();
    await expect(body).toBeVisible();
  } else {
    await expect(toggle).toHaveAccessibleName("Show legend");
    await expect(toggle.locator(".hud-scotland-fold-show")).toBeVisible();
    await expect(toggle.locator(".hud-scotland-fold-hide")).toBeHidden();
    await expect(body).toBeHidden();
  }
}

async function assertCreditAndZoomClear(page: Page) {
  const credit = await creditLine(page);
  await assertUncovered(credit, "Registers of Scotland credit");
  await assertUncovered(page.locator(".maplibregl-ctrl-zoom-in"), "zoom-in button");
  await assertUncovered(page.locator(".maplibregl-ctrl-zoom-out"), "zoom-out button");
}

async function creditLine(page: Page) {
  await openAttributionIfCollapsed(page);
  const credit = page
    .locator(".maplibregl-ctrl-attrib-inner")
    .filter({ hasText: "Registers of Scotland" });
  await expect(credit).toContainText("Registers of Scotland");
  return credit;
}

async function revealLongCredit(page: Page) {
  await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText("OpenFreeMap", {
    timeout: 30_000,
  });
  await panToGlasgow(page);
  const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  for (let step = 0; step < 12; step += 1) {
    const ready = await attrib.textContent();
    if (ready?.includes("Registers of Scotland")) break;
    await zoomIn.click({ timeout: 10_000 });
    await page.waitForTimeout(600);
  }
  await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText(
    "Registers of Scotland",
    { timeout: 20_000 },
  );
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
        covers.push(`${name} at (${point.x.toFixed(1)}, ${point.y.toFixed(1)})`);
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
  expect(result.covers, `${label} is covered by ${result.covers.join("; ")}`).toEqual(
    [],
  );
}
