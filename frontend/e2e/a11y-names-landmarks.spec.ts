import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

/**
 * UX-04 — accessible names on buttons; unique landmark labels.
 * axe: zero button-name and landmark-unique failures.
 * Console / pageerror fail the test (do not loosen).
 */

const consoleErrors: string[] = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const CATALOG = {
  version: 2,
  layers: [
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      attribution:
        "© Crown copyright. Reproduced with the permission of Registers of Scotland.",
      source_url: "https://www.ros.gov.uk/open-data",
    },
  ],
};

const PLACE_STUB = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
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

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/parcels/i.test(url);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
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
      body: JSON.stringify(CATALOG),
    });
  });
  await page.route("**/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(CATALOG),
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
      body: JSON.stringify({ code: null, name: null, vintage: null }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
}

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  await stubMapBackend(page);
});

test.afterEach(() => {
  expect(consoleErrors, `console/pageerror:\n${consoleErrors.join("\n")}`).toEqual(
    [],
  );
});

test.describe("UX-04 a11y names and landmarks at 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("axe button-name and landmark-unique are clean with layers and credits", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    // Source guard: MapLibre popup close is a bare × unless we name it.
    const scotlandMap = readFileSync(
      join(process.cwd(), "components/ScotlandMap.tsx"),
      "utf8",
    );
    expect(scotlandMap).toContain('aria-label", "Close popup"');
    expect(scotlandMap).toContain('aria-label="Map legend"');
    expect(scotlandMap).not.toContain('aria-label="Land rent"');

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator("#place-query").waitFor();

    // Open Layers drawer — must not create a second complementary "Layers".
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();

    await expect(
      page.getByRole("complementary", { name: "Map legend", exact: true }),
    ).toHaveCount(1);
    await expect(
      page.getByRole("complementary", { name: "Map layers", exact: true }),
    ).toHaveCount(1);
    await expect(
      page.getByRole("complementary", { name: "Layers", exact: true }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("complementary", { name: "Land rent", exact: true }),
    ).toHaveCount(0);

    // Enable parcels so MapLicenceCredits mounts (unique group name, not a landmark).
    await page.getByTestId("layer-toggle-boundaries").click();
    await expect(page.getByTestId("map-licence-credits")).toBeVisible({
      timeout: 15_000,
    });
    await expect(
      page.getByRole("group", { name: "Map data licences", exact: true }),
    ).toHaveCount(1);
    await expect(
      page.getByRole("complementary", {
        name: "Map data licences",
        exact: true,
      }),
    ).toHaveCount(0);

    // Search stays named while the control shows "…"
    await expect(page.getByRole("button", { name: "Search", exact: true })).toHaveCount(
      1,
    );

    const results = await new AxeBuilder({ page })
      .withRules(["button-name", "landmark-unique"])
      .analyze();

    expect(
      results.violations,
      results.violations
        .map(
          (v) =>
            `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join("; ")}`,
        )
        .join("\n") || "axe violations",
    ).toEqual([]);

    // No public £ on the map chrome we touched.
    await expect(page.locator("body")).not.toContainText(/£\d/);
  });
});
