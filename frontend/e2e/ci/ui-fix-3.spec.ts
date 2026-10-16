import { expect, test, type Page } from "@playwright/test";

/**
 * UI-FIX-3 — one close control, no empty block under the disclaimer.
 * Yellow rule selector from the place panel: `.map-panel-slot-focus`
 * (GOV.UK outline #ffdd00 in map-chrome.css). The empty tail is the
 * place card box below `[data-testid="place-card-footer"]`.
 * 390×844 and 1280×800. Three places. Asserts can fail.
 */

const PLACES = ["EH1 1YZ", "Inverness", "IV27 4HN"] as const;

const COORDS: Record<(typeof PLACES)[number], { lat: number; lng: number }> = {
  "EH1 1YZ": { lat: 55.9533, lng: -3.1883 },
  Inverness: { lat: 57.4778, lng: -4.2247 },
  "IV27 4HN": { lat: 58.419, lng: -4.762 },
};

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const YELLOW_RULE = ".map-panel-slot-focus";

function cardFor(label: string, lat: number, lng: number) {
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: label,
    council_name: "Council",
    data_zone: {
      status: "ok",
      code: "S01008677",
      name: "Zone",
      vintage: 2022,
    },
    intermediate_zone: { status: "ok", name: "IZ", code: "S02001607" },
    agr_rows: [
      {
        id: "surface",
        label: "Land",
        tag: "proxy",
        status: "in_progress",
        applies: true,
      },
    ],
    constraints: [],
    layers: [],
    links: [],
  };
}

async function stubMap(page: Page) {
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
    const url = route.request().url();
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      const u = new URL(url);
      const lat = Number(u.searchParams.get("lat"));
      const hit =
        PLACES.map((name) => ({ name, ...COORDS[name] })).find(
          (p) => Math.abs(p.lat - lat) < 0.05,
        ) ?? { name: "EH1 1YZ", ...COORDS["EH1 1YZ"] };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(cardFor(hit.name, hit.lat, hit.lng)),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      const u = new URL(url);
      const q = u.searchParams.get("q") ?? "";
      const name = PLACES.find(
        (p) => p.toLowerCase() === q.trim().toLowerCase(),
      );
      const hit = name ? { name, ...COORDS[name] } : null;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          hit
            ? { kind: "point", lat: hit.lat, lng: hit.lng, label: hit.name }
            : { kind: "places", matches: [] },
        ),
      });
      return;
    }
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/boundaries\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/parcels/i.test(url);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
    });
  });
}

async function openCard(page: Page, query: string) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const input = page.locator("#place-query");
  await input.fill(query);
  await page.locator(".hud-search-go").click();
  await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("place-card-close")).toBeVisible();
  await expect(page.getByTestId("place-card-footer")).toBeVisible();
  await expect(page.getByTestId("place-card-placeholders")).toHaveCount(0);
  await expect(page.getByTestId("place-card-place")).toBeVisible({
    timeout: 30_000,
  });
}

type EmptyAudit = {
  closeCount: number;
  emptyAfter: { selector: string; height: number }[];
  yellowRule: { selector: string; height: number; visible: boolean };
  tail: number;
};

async function auditOpenCard(page: Page): Promise<EmptyAudit> {
  return page.getByTestId("map-panel-slot").evaluate((slot, yellowSelector) => {
    const scroll = slot.querySelector('[data-testid="map-panel-scroll"]');
    if (scroll) scroll.scrollTop = scroll.scrollHeight;

    const card = slot.querySelector('[data-testid="place-card"]');
    const footer = slot.querySelector('[data-testid="place-card-footer"]');
    if (!footer || !card) {
      return {
        closeCount: 0,
        emptyAfter: [{ selector: "missing-footer", height: 99 }],
        yellowRule: { selector: yellowSelector, height: 99, visible: true },
        tail: 99,
      };
    }
    const fb = footer.getBoundingClientRect();
    const nodes = [...slot.querySelectorAll("*")];
    const footerIndex = nodes.indexOf(footer);
    const emptyAfter: { selector: string; height: number }[] = [];
    for (const el of nodes.slice(footerIndex + 1)) {
      if (footer.contains(el)) continue;
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const visible =
        r.width > 0 &&
        r.height > 0 &&
        cs.visibility !== "hidden" &&
        cs.display !== "none" &&
        Number(cs.opacity) !== 0;
      if (!visible) continue;
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (text.length === 0 && r.height > 8) {
        const selector =
          el.getAttribute("data-testid") ||
          (typeof el.className === "string" ? el.className : el.tagName);
        emptyAfter.push({ selector, height: r.height });
      }
    }

    let closeCount = 0;
    for (const el of slot.querySelectorAll("button, [role='button']")) {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const visible =
        r.width > 0 &&
        r.height > 0 &&
        cs.visibility !== "hidden" &&
        cs.display !== "none" &&
        Number(cs.opacity) !== 0;
      if (!visible) continue;
      const name = (el.getAttribute("aria-label") || "").trim();
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (/close/i.test(name) || text === "×" || text === "✕") closeCount += 1;
    }

    const focus = slot.querySelector(yellowSelector);
    let yellowHeight = 0;
    let yellowVisible = false;
    if (focus) {
      const cs = getComputedStyle(focus);
      const r = focus.getBoundingClientRect();
      const paintsYellow =
        cs.outlineStyle !== "none" &&
        parseFloat(cs.outlineWidth) > 0 &&
        /255,\s*221,\s*0/.test(cs.outlineColor) &&
        r.bottom > fb.bottom - 1 &&
        r.width > 0 &&
        r.height > 0 &&
        cs.visibility !== "hidden" &&
        cs.display !== "none";
      yellowVisible = paintsYellow;
      yellowHeight = paintsYellow ? Math.max(r.height, parseFloat(cs.outlineWidth)) : 0;
    }

    const tail = card.getBoundingClientRect().bottom - fb.bottom;
    return {
      closeCount,
      emptyAfter,
      yellowRule: {
        selector: yellowSelector,
        height: yellowHeight,
        visible: yellowVisible,
      },
      tail,
    };
  }, YELLOW_RULE);
}

for (const viewport of [
  { width: 390, height: 844 },
  { width: 1280, height: 800 },
] as const) {
  test.describe(`UI-FIX-3 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    for (const query of PLACES) {
      test(`${query}: one close, no empty block under disclaimer`, async ({
        page,
      }) => {
        test.setTimeout(90_000);
        await stubMap(page);
        await openCard(page, query);
        const audit = await auditOpenCard(page);
        const slot = page.getByTestId("map-panel-slot");
        const namedClose = slot.getByRole("button", { name: /close/i });
        await expect(namedClose, `accessible close for ${query}`).toHaveCount(1);
        await expect(page.getByTestId("place-card-close")).toHaveCount(1);
        await expect(namedClose).toHaveAttribute("data-testid", "place-card-close");
        const crossCount = await slot.locator("button").evaluateAll((buttons) => {
          return buttons.filter((el) => {
            const r = el.getBoundingClientRect();
            const cs = getComputedStyle(el);
            const visible =
              r.width > 0 &&
              r.height > 0 &&
              cs.visibility !== "hidden" &&
              cs.display !== "none" &&
              Number(cs.opacity) !== 0;
            if (!visible) return false;
            const text = (el.textContent || "").replace(/\s+/g, " ").trim();
            return text === "×" || text === "✕";
          }).length;
        });
        expect(crossCount, `× close controls for ${query}`).toBe(1);
        expect(audit.closeCount, `visible close controls for ${query}`).toBe(1);
        expect(
          audit.emptyAfter,
          `empty descendants after disclaimer for ${query}`,
        ).toEqual([]);
        expect(
          audit.yellowRule.visible,
          `${audit.yellowRule.selector} yellow rule visible`,
        ).toBe(false);
        expect(
          audit.yellowRule.height,
          `${audit.yellowRule.selector} yellow rule height`,
        ).toBe(0);
        expect(
          audit.tail,
          `empty block below disclaimer (.hud-place / ${YELLOW_RULE}) h=${audit.tail}`,
        ).toBeLessThanOrEqual(8);
      });
    }
  });
}
