import { expect, test, type Page } from "@playwright/test";

const POSTCODE = "EH1 1YZ";
/** Four public group names — same as Layers and /data. */
const APPROVED_VALUE_HEADINGS = [
  "Land",
  "Natural resource rents",
  "Services of nature",
] as const;
const APPROVED_LIMITS_HEADING = "Limits";
const FIGURE_WHY =
  "Figures will appear once the valuation rules are signed off.";

const EMPTY_FC = JSON.stringify({
  type: "FeatureCollection",
  features: [],
});

/** Full place_card_v1 with three approved rent-group rows (no £). */
function placeCardBody(overrides: Record<string, unknown> = {}) {
  return {
    contract: "place_card_v1",
    lat: 55.952,
    lng: -3.189,
    place_label: "Edinburgh Old Town",
    postcode: POSTCODE,
    council_name: "City of Edinburgh",
    data_zone: {
      status: "ok",
      code: "S01008677",
      name: "Old Town",
      vintage: 2022,
    },
    intermediate_zone: {
      status: "ok",
      code: "S02002727",
      name: "Old Town, Princes Street and Leith Street",
    },
    square_reference: "Scot-LAND square reference 123,456",
    agr_rows: [
      {
        id: "surface",
        label: "Land",
        tag: "proxy",
        status: "in_progress",
        applies: true,
        of_which: [{ id: "planning_uplift", label: "of which: planning uplift" }],
      },
      {
        id: "resource",
        label: "Natural resource rents",
        tag: "market",
        status: "coming_soon",
        applies: true,
      },
      {
        id: "nature",
        label: "Services of nature",
        tag: "shadow",
        status: "coming_soon",
        applies: true,
      },
    ],
    constraints: [],
    layers: [],
    links: [],
    ...overrides,
  };
}

/** Legacy live labels — must remap to Land / NRR / SoN in the card. */
function placeCardBodyLegacyLabels() {
  return placeCardBody({
    agr_rows: [
      {
        id: "surface",
        label: "Surface",
        tag: "proxy",
        status: "in_progress",
        applies: true,
        of_which: [{ id: "planning_uplift", label: "of which: planning uplift" }],
      },
      {
        id: "resource",
        label: "Resource",
        tag: "market",
        status: "coming_soon",
        applies: true,
      },
      {
        id: "nature",
        label: "Nature",
        tag: "shadow",
        status: "coming_soon",
        applies: true,
      },
    ],
  });
}

function attachConsoleTraps(page: Page): string[] {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    if (
      /Failed to load resource: the server responded with a status of/.test(
        text,
      )
    ) {
      return;
    }
    consoleErrors.push(text);
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  return consoleErrors;
}

async function stubMapBackend(
  page: Page,
  opts: { legacyAgrLabels?: boolean } = {},
) {
  await page.route("**/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.endsWith("/health") || path.includes("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          routers: {
            "api.agr_routes": { loaded: true },
            "api.platform_routes": { loaded: true },
          },
        }),
      });
      return;
    }

    if (path.includes("/place") && !path.includes("/platform/place")) {
      const q = (url.searchParams.get("q") || "")
        .toUpperCase()
        .replace(/\s+/g, " ");
      if (q.includes("EH1")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            kind: "postcode",
            postcode: POSTCODE,
            lat: 55.952,
            lng: -3.189,
            label: POSTCODE,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "none", note: "No matches" }),
      });
      return;
    }

    if (path.includes("/postcode/")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          postcode: { postcode: POSTCODE },
          lat: 55.952,
          lng: -3.189,
          square: { lat: 55.952, lng: -3.189 },
        }),
      });
      return;
    }

    if (path.includes("/platform/place")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          opts.legacyAgrLabels ? placeCardBodyLegacyLabels() : placeCardBody(),
        ),
      });
      return;
    }

    if (path.includes("/layers/catalog") || path.endsWith("/catalog")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: EMPTY_FC,
    });
  });
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  const dismiss = page.getByTestId("research-banner-dismiss");
  if (await dismiss.count()) {
    await dismiss.click({ force: true });
  }
}

async function expectApprovedPlaceCard(page: Page) {
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 30_000 });

  for (const heading of APPROVED_VALUE_HEADINGS) {
    await expect(card.getByTestId("place-card-value")).toContainText(heading);
  }
  await expect(card.getByTestId("place-card-limits")).toContainText(
    APPROVED_LIMITS_HEADING,
  );
  await expect(card.getByTestId("place-card-value")).not.toContainText(
    /\bSurface\b/,
  );
  await expect(card.getByTestId("place-card-value")).not.toContainText(
    /\bResource\b/,
  );
  // Bare "Nature" heading banned; "Services of nature" is the approved label.
  await expect(card.getByTestId("place-card-agr-nature")).toContainText(
    "Services of nature",
  );
  await expect(card.getByTestId("place-card-agr-nature")).not.toHaveText(
    /^Nature$/,
  );
  await expect(card.getByTestId("place-card-limits")).not.toContainText(
    "What limits how it's used",
  );

  await expect(card.getByText("Map reference", { exact: true })).toBeVisible();
  await expect(page.getByTestId("place-card-map-reference")).toContainText(
    /Scot-LAND square reference/i,
  );
  await expect(page.getByTestId("place-card-map-reference-copy")).toBeVisible();

  await expect(page.getByTestId("place-value-status-in_progress")).toHaveText(
    "Figure not published yet",
  );
  await expect(page.getByTestId("place-card-figure-why").first()).toHaveText(
    "Why?",
  );
  await expect(
    page.getByTestId("place-card-figure-why-text").first(),
  ).toHaveText(FIGURE_WHY);

  await expect(card.getByText(/£\d/)).toHaveCount(0);
  await expect(card).not.toContainText("£0");
}

test.describe("SW-021 shared place card headings", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("postcode EH1 1YZ and map click show the same approved headings", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page);
    await openMap(page);

    // --- Postcode search path ---
    const search = page.locator("#place-query");
    await search.fill(POSTCODE);
    await expect(page.getByRole("option", { name: POSTCODE })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("option", { name: POSTCODE }).click();
    await expectApprovedPlaceCard(page);

    // Close card so map click can reopen it.
    const close = page.getByRole("button", { name: "Close place card" });
    if (await close.count()) {
      await close.click();
    }

    // --- Map click path (same shared PlaceCard) ---
    const canvas = page.locator(".maplibregl-canvas");
    const box = await canvas.boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
    await expectApprovedPlaceCard(page);

    expect(
      consoleErrors,
      `console errors:\n${consoleErrors.join("\n")}`,
    ).toEqual([]);
  });

  test("legacy Surface/Resource/Nature API labels remap to approved four groups", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page, { legacyAgrLabels: true });
    await openMap(page);

    const search = page.locator("#place-query");
    await search.fill(POSTCODE);
    await expect(page.getByRole("option", { name: POSTCODE })).toBeVisible({
      timeout: 15_000,
    });
    await page.getByRole("option", { name: POSTCODE }).click();
    await expectApprovedPlaceCard(page);

    expect(
      consoleErrors,
      `console errors:\n${consoleErrors.join("\n")}`,
    ).toEqual([]);
  });
});
