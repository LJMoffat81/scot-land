/**
 * CARD-CLARITY-31OCT-1A — site chrome & wording (PR A).
 * Unit / negative / e2e locks for items 1, 2, 3-5, 6, 9, 10.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  injectEsriBasemapKey,
  openMap,
  readCreditShortNames,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import { POSTCODES_ONLY } from "../../lib/api";
import {
  GRID3_SQUARE_PREFIX,
  grid3GridSquareLabel,
  grid3Row6Text,
} from "../../lib/bng";
import { BASEMAP_SWITCHER_VISIBLE_LABEL } from "../../lib/mapBasemap";
import { SEARCH_PLACEHOLDER, SITE_NAV_ITEMS } from "../../lib/siteNav";
import {
  MAP_CREDIT_SIMPLE,
  mapCreditSourcesText,
} from "../../components/MapCreditLine";
import { PANEL_TAB_SHOW_PLACE_DETAILS } from "../../components/MapPanelSlot";

registerOpenFreeMapFontStub();

const FRONTEND_ROOT = join(__dirname, "..", "..");

const RETIRED = [
  "Downloads & API",
  "Reopen place card",
  "Search a postcode, e.g. G2 1DU",
  "Search a postcode or place",
  "3m grid square:",
] as const;

function stripCommentsAndScreamingIds(src: string): string {
  let out = src.replace(/\/\*[\s\S]*?\*\//g, " ");
  out = out.replace(/(^|[^:])\/\/.*$/gm, "$1");
  out = out.replace(/\b[A-Z][A-Z0-9_]{2,}\b/g, " ");
  return out;
}

function listSourceFiles(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next" || name === "dist") continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      listSourceFiles(full, out);
      continue;
    }
    if (/\.(ts|tsx|js|jsx|mjs)$/.test(name)) out.push(full);
  }
  return out;
}

test("CC-A-U1 locked chrome wording constants", () => {
  expect(SITE_NAV_ITEMS.map((i) => i.label)).toEqual([
    "Map",
    "About",
    "How it works",
    "Data & sources",
    "Get the data",
  ]);
  const navIds = SITE_NAV_ITEMS.map((i) => i.id as string);
  const navLabels = SITE_NAV_ITEMS.map((i) => i.label as string);
  expect(navIds).not.toContain("built");
  expect(navLabels).not.toContain("How we built this");
  expect(navLabels).not.toContain("Downloads & API");

  expect(SEARCH_PLACEHOLDER).toBe("Search a postcode, or tap the map");
  expect(POSTCODES_ONLY).toBe(
    "Search finds full UK postcodes only (e.g. G2 1DU). Or tap or click the map.",
  );
  expect(BASEMAP_SWITCHER_VISIBLE_LABEL).toBe("Aerial");

  expect(GRID3_SQUARE_PREFIX).toBe("3 m grid square:");
  expect(grid3GridSquareLabel("NT 25890 73452")).toBe(
    "3 m grid square: NT 25890 73452",
  );
  expect(grid3Row6Text("NT 25890 73452")).toBe(
    "3 m grid square: NT 25890 73452 (a map grid, not a property)",
  );
  expect(grid3Row6Text("NT 25890 73452")).not.toMatch(/^Grid square /);
  expect(grid3GridSquareLabel("NT 25890 73452")).not.toMatch(/^3m grid square:/);

  expect(PANEL_TAB_SHOW_PLACE_DETAILS).toBe("Show place details");
  expect(mapCreditSourcesText(3)).toBe("Sources (3)");
  expect(mapCreditSourcesText(1)).toBe("Sources (1)");
  expect(MAP_CREDIT_SIMPLE).toBe(
    "© OpenFreeMap © OpenStreetMap · Sources (1)",
  );
});

test("CC-A-N1 mapCreditSourcesText refuses bad counts", () => {
  for (const bad of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
    expect(mapCreditSourcesText(bad)).toBe("Sources");
    expect(mapCreditSourcesText(bad)).not.toMatch(/Sources \(\d/);
  }
});

test("CC-A-N2 no neighbourhood in app/components/lib visitor source", () => {
  const roots = ["app", "components", "lib"].map((d) =>
    join(FRONTEND_ROOT, d),
  );
  const hits: string[] = [];
  const re = /neighbou?rhood/i;
  for (const root of roots) {
    for (const file of listSourceFiles(root)) {
      const raw = readFileSync(file, "utf8");
      const scanned = stripCommentsAndScreamingIds(raw);
      if (re.test(scanned)) {
        hits.push(relative(FRONTEND_ROOT, file));
      }
    }
  }
  expect(hits).toEqual([]);
});

test("CC-A-N3 retired chrome strings absent from app/components/lib", () => {
  const roots = ["app", "components", "lib"].map((d) =>
    join(FRONTEND_ROOT, d),
  );
  const hits: string[] = [];
  for (const root of roots) {
    for (const file of listSourceFiles(root)) {
      const raw = readFileSync(file, "utf8");
      // Nav item "How we built this" must be gone from siteNav; page heading may remain.
      if (file.endsWith(`${join("lib", "siteNav.ts")}`)) {
        if (raw.includes('"How we built this"') || raw.includes("'How we built this'")) {
          hits.push(`${relative(FRONTEND_ROOT, file)}: nav How we built this`);
        }
      }
      for (const old of RETIRED) {
        if (raw.includes(old)) {
          hits.push(`${relative(FRONTEND_ROOT, file)}: ${old}`);
        }
      }
    }
  }
  expect(hits).toEqual([]);
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`CC-A-E chrome ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("placeholder, Aerial label, Sources (N) bar without short name", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await injectEsriBasemapKey(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/?layers=vdl&z=12&c=-4.25,55.86");
      await waitForMap(page);

      await expect(page.locator("#place-query")).toHaveAttribute(
        "placeholder",
        SEARCH_PLACEHOLDER,
      );
      await expect(page.locator("#place-query")).not.toHaveAttribute(
        "placeholder",
        "Search a postcode, e.g. G2 1DU",
      );

      await expect(page.getByTestId("basemap-switcher-label")).toHaveText(
        "Aerial",
      );

      const credit = page.getByTestId("map-credit-line");
      await expect(credit).toBeVisible();
      const bar = ((await credit.innerText()) ?? "").replace(/\s+/g, " ").trim();
      expect(bar).toMatch(/Sources \(\d+\)/);
      expect(bar).not.toContain("Vacant land: SVDLS");
      expect(bar).not.toMatch(/Sources$/);

      const short = await readCreditShortNames(page);
      expect(short).toContain("Vacant land: SVDLS");
      assertConsoleClean(gate);
    });
  });
}

test.describe("CC-A-E nav", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("nav drops How we built this; Get the data; methodology section; page marks How it works", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await openMap(page);
    await waitForMap(page);

    const nav = page.getByTestId("site-nav");
    await expect(
      nav.getByRole("link", { name: "How we built this", exact: true }),
    ).toHaveCount(0);
    await expect(
      nav.getByRole("link", { name: "Get the data", exact: true }),
    ).toBeVisible();
    await expect(
      nav.getByRole("link", { name: "Downloads & API", exact: true }),
    ).toHaveCount(0);

    await page.goto("/methodology");
    const section = page.getByTestId("methodology-how-we-built");
    await expect(section).toBeVisible();
    await expect(
      section.getByRole("heading", { name: "How we built this", exact: true }),
    ).toBeVisible();
    await expect(section.locator("a[href='/how-we-built-this']")).toBeVisible();
    await expect(section).not.toContainText("Laurie");
    await expect(section).not.toContainText("Moffat");

    await page.goto("/how-we-built-this");
    await expect(
      page.getByTestId("site-nav").getByRole("link", {
        name: "How it works",
        exact: true,
      }),
    ).toHaveAttribute("aria-current", "page");
    assertConsoleClean(gate);
  });
});
