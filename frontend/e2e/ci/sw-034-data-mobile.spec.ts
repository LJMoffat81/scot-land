import { registerOpenFreeMapFontStub, stubMapCardsBackend } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Locator, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * SW-034 — mobile /data sources as stacked cards (below 640px).
 * At 390: no horizontal page scroll; every source Licence + Link in viewport
 * after scroll. At 1280: desktop table with all columns. No £ / banned words.
 */

const BANNED =
  /\b(natural capital|ledger|headline|shadow|yield|what3words)\b/i;

const GROUP_NAMES = [
  "Land",
  "Natural resource rents",
  "Services of nature",
] as const;

const CATALOG = {
  layers: [
    {
      id: "vdl",
      label: "Vacant and derelict land",
      description: "Survey sites of vacant and derelict land.",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url: "https://www.gov.scot/",
      group: "spatial",
    },
    {
      id: "repd_onshore_wind",
      label: "Onshore wind",
      description: "Onshore wind planning sites.",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url: "https://www.gov.uk/",
      ledger_row: "3",
    },
    {
      id: "nfi",
      label: "National Forest Inventory",
      description: "Woodland of half a hectare or more.",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url: "https://www.forestresearch.gov.uk/",
      ledger_row: "1",
    },
    {
      id: "sssi",
      label: "SSSI",
      description: "Sites of Special Scientific Interest.",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url: "https://opendata.nature.scot/",
      ledger_role: "constraint",
    },
  ],
};

const SOURCE_IDS = CATALOG.layers.map((layer) => layer.id);

function isCatalogRequest(url: string): boolean {
  return /\/(?:backend\/)?api\/catalog\.json(?:\?|$)/i.test(url);
}

async function mockCatalog(page: Page) {
  // Browser fetch is /backend/api/catalog.json on localhost; also cover /api/.
  await page.route(
    (url) => isCatalogRequest(url.href),
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CATALOG),
      });
    },
  );
}

async function gotoDataWithCatalog(page: Page) {
  // stubMapCardsBackend first; mockCatalog (caller) registers after so LIFO wins.
  const catalogOk = page.waitForResponse(
    (res) => isCatalogRequest(res.url()) && res.ok(),
  );
  await page.goto("/data");
  await catalogOk;
  await expect(
    page.getByRole("heading", { name: "Data & sources" }),
  ).toBeVisible();
  await expect(page.getByTestId("data-sources-groups")).toBeVisible();
}

async function openAllGroups(page: Page) {
  const groups = page.locator("[data-testid^='data-sources-group-']");
  // count() does not wait — groups render after the catalog fetch.
  await expect(
    groups.first(),
    "sources groups should render after catalog load",
  ).toBeVisible({ timeout: 15_000 });
  const count = await groups.count();
  expect(count).toBeGreaterThan(0);
  for (let i = 0; i < count; i += 1) {
    const group = groups.nth(i);
    const open = await group.getAttribute("open");
    if (open === null) {
      await group.locator("summary").click();
    }
    await expect(group).toHaveAttribute("open", "");
  }
}

async function assertInViewport(locator: Locator, label: string) {
  await locator.scrollIntoViewIfNeeded();
  await expect(locator, label).toBeVisible();
  await expect(locator, `${label} in viewport`).toBeInViewport();
  const box = await locator.boundingBox();
  expect(box, `${label} bounding box`).toBeTruthy();
  if (!box) return;
  const viewport = locator.page().viewportSize();
  expect(viewport, `${label} viewport`).toBeTruthy();
  if (!viewport) return;
  expect(box.x, `${label} clipped left`).toBeGreaterThanOrEqual(-0.5);
  expect(box.x + box.width, `${label} clipped right`).toBeLessThanOrEqual(
    viewport.width + 0.5,
  );
}

test.describe("SW-034 /data mobile source cards", () => {
  test("390: cards, no horizontal scroll, licence and link in viewport", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await stubMapCardsBackend(page);
    await mockCatalog(page);
    await gotoDataWithCatalog(page);
    await openAllGroups(page);

    // Table hidden; cards shown.
    await expect(page.locator(".sources-table-wrap").first()).toBeHidden();
    await expect(page.getByTestId("data-source-card-vdl")).toBeVisible();

    const scroll = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      innerWidth: window.innerWidth,
    }));
    expect(
      scroll.scrollWidth,
      "document must not scroll horizontally",
    ).toBeLessThanOrEqual(Math.max(scroll.clientWidth, scroll.innerWidth) + 1);

    for (const id of SOURCE_IDS) {
      const card = page.getByTestId(`data-source-card-${id}`);
      await assertInViewport(card, `card ${id}`);
      const licence = page.getByTestId(`data-source-licence-${id}`);
      const link = page.getByTestId(`data-source-link-${id}`);
      await assertInViewport(licence, `licence ${id}`);
      await assertInViewport(link, `link ${id}`);
    }

    const bodyText = await page.locator("main").innerText();
    expect(bodyText).not.toContain("£");
    expect(bodyText).not.toMatch(/£\d/);
    expect(bodyText).not.toMatch(BANNED);
    for (const name of GROUP_NAMES) {
      expect(bodyText).toContain(name);
    }
  });

  test("1280: desktop table with all columns", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await stubMapCardsBackend(page);
    await mockCatalog(page);
    await gotoDataWithCatalog(page);
    await openAllGroups(page);

    const landTable = page.getByTestId("data-sources-table-land");
    await expect(landTable).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("data-source-card-vdl")).toBeHidden();

    await expect(landTable.getByRole("columnheader", { name: "Source" })).toBeVisible();
    await expect(
      landTable.getByRole("columnheader", { name: "What it shows" }),
    ).toBeVisible();
    await expect(
      landTable.getByRole("columnheader", { name: "Licence" }),
    ).toBeVisible();
    await expect(landTable.getByRole("columnheader", { name: "Link" })).toBeVisible();

    // Licence and Link cells for the land-group fixture row.
    const vdlRow = landTable.locator("tr[data-source-id='vdl']");
    await expect(vdlRow.getByRole("link", { name: "OGL-3.0" })).toBeVisible();
    await expect(vdlRow.getByRole("link", { name: "Source" })).toBeVisible();

    const bodyText = await page.locator("main").innerText();
    expect(bodyText).not.toContain("£");
    expect(bodyText).not.toMatch(BANNED);
    for (const name of GROUP_NAMES) {
      expect(bodyText).toContain(name);
    }
  });
});
