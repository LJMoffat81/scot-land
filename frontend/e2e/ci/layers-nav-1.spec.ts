import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  LIVE_LAYER_IDS,
  openLayers,
  openMap,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();


/**
 * LAYERS-NAV-1 — two headers, three LAND sub-groups, roadmap rent rows.
 * The roadmap “What we aim to cover” list is the source of truth.
 */

const HEADER_ORDER = [
  "LAND",
  "Sites",
  "Natural resources",
  "Services of nature",
  "PLACES AND BOUNDARIES",
] as const;

const PARKED_NAMES = [
  "Site rent: business",
  "Licences and franchises",
  "Radio spectrum",
] as const;

type AimScraped = {
  id: string;
  name: string;
  status: string;
};

function panelTag(status: string): string {
  if (status === "Later") return "Coming later";
  if (status === "In progress") return "In progress";
  if (status === "Not started") return "Coming later";
  if (status === "Live") return "Live";
  throw new Error(`unexpected roadmap status: ${status}`);
}

async function scrapeAimRows(page: Page): Promise<AimScraped[]> {
  await page.goto("/roadmap");
  const section = page.getByTestId("roadmap-aim");
  await expect(section).toBeVisible();
  return section.getByTestId("roadmap-aim-row").evaluateAll((els) =>
    els.map((el) => ({
      id: el.id,
      name: el.querySelector(".roadmap-layer-name")?.textContent?.trim() ?? "",
      status:
        el.querySelector("[data-testid='roadmap-aim-status']")?.textContent?.trim() ??
        "",
    })),
  );
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`LAYERS-NAV-1 (${viewport.width})`, () => {
    test.use({ viewport });

    test("headers, sub-groups, same switches, roadmap rows", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      const aim = await scrapeAimRows(page);
      expect(aim.length).toBeGreaterThan(PARKED_NAMES.length);
      for (const row of aim) {
        expect(row.id, row.name).toMatch(/^[a-z0-9-]+$/);
        expect(row.name).not.toBe("");
      }
      for (const name of PARKED_NAMES) {
        expect(aim.filter((row) => row.name === name)).toHaveLength(1);
      }

      const parked = new Set<string>(PARKED_NAMES);
      const shown = aim.filter((row) => !parked.has(row.name));

      await openMap(page);
      await openLayers(page);
      for (const key of ["land", "resources", "nature", "places"] as const) {
        await ensureLayersGroupOpen(page, key);
      }

      const panel = page.getByTestId("layers-panel");
      const order = await page
        .locator(
          "[data-testid='layers-nav-header'], [data-testid='layers-nav-subgroup']",
        )
        .allInnerTexts();
      expect(order.map((line) => line.trim())).toEqual([...HEADER_ORDER]);
      await expect(page.getByTestId("layers-nav-header")).toHaveCount(2);
      await expect(page.getByTestId("layers-nav-subgroup")).toHaveCount(3);
      await expect(page.getByTestId("layers-nav-land-subtitle")).toHaveText(
        "Everything nature provides and no one made",
      );
      await expect(page.getByTestId("layers-nature-note")).toHaveText(
        "Estimates only. Never taxed.",
      );
      await expect(
        page
          .getByTestId("layers-nav-land")
          .getByTestId("map-layers-limits-explainer"),
      ).toContainText("Limits on use");
      await expect(
        page
          .getByTestId("layers-nav-places")
          .getByTestId("map-layers-limits-explainer"),
      ).toHaveCount(0);

      const placesText = await page.getByTestId("layers-nav-places").innerText();
      expect(placesText).not.toContain("£");
      expect(placesText.toLowerCase()).not.toContain("rent");
      await expect(
        panel.getByRole("switch", { name: "Area boundaries", exact: true }),
      ).toHaveCount(1);

      const switchIds = (
        await panel.locator("[data-testid^='layer-toggle-']").evaluateAll((els) =>
          els.map((el) =>
            (el.getAttribute("data-testid") ?? "").replace(/^layer-toggle-/, ""),
          ),
        )
      ).sort();
      expect(switchIds).toEqual([...LIVE_LAYER_IDS].sort());

      const panelLines = (await panel.innerText())
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0);

      for (const name of PARKED_NAMES) {
        expect(panelLines.filter((line) => line === name)).toEqual([]);
        await expect(panel.getByText(name, { exact: true })).toHaveCount(0);
      }

      const placeholderRows: AimScraped[] = [];
      for (const row of shown) {
        expect(
          panelLines.filter((line) => line === row.name),
          row.name,
        ).toHaveLength(1);
        const liveSwitch = panel.getByRole("switch", {
          name: row.name,
          exact: true,
        });
        const placeholder = panel.getByTestId(`layers-aim-${row.id}`);
        if ((await liveSwitch.count()) === 1) {
          await expect(placeholder).toHaveCount(0);
          await expect(liveSwitch).toHaveAttribute("role", "switch");
          continue;
        }
        await expect(liveSwitch).toHaveCount(0);
        await expect(placeholder).toHaveCount(1);
        await expect(placeholder.locator("[aria-disabled='true']")).toHaveCount(1);
        await expect(placeholder.locator("[aria-disabled='true']")).toHaveAttribute(
          "aria-label",
          `${row.name}, ${panelTag(row.status)}`,
        );
        await expect(placeholder.getByRole("link")).toHaveCount(1);
        await expect(
          placeholder.locator("[aria-disabled='true']").getByRole("link"),
        ).toHaveCount(0);
        await expect(placeholder.getByRole("switch")).toHaveCount(0);
        await expect(placeholder.getByTestId(`layers-aim-tag-${row.id}`)).toHaveText(
          panelTag(row.status),
        );
        await expect(
          placeholder.getByTestId(`layers-aim-link-${row.id}`),
        ).toHaveAttribute("href", `/roadmap#${row.id}`);
        const text = await placeholder.innerText();
        expect(text).not.toContain("£");
        expect(text).not.toMatch(/\d/);
        placeholderRows.push(row);
      }

      expect(placeholderRows.length).toBeGreaterThan(0);
      const linkRow = placeholderRows[0]!;
      await page.getByTestId(`layers-aim-link-${linkRow.id}`).click();
      await expect(page).toHaveURL(new RegExp(`/roadmap#${linkRow.id}$`));
      await expect(page.locator(`#${linkRow.id}`)).toBeVisible();
      await expect(page.locator(`#${linkRow.id}`)).toContainText(linkRow.name);

      for (const row of placeholderRows) {
        await page.goto(`/roadmap#${row.id}`);
        const anchor = page.locator(`#${row.id}`);
        await expect(anchor).toBeVisible();
        await expect(anchor).toContainText(row.name);
        await expect(anchor.getByTestId("roadmap-aim-status")).toHaveText(
          row.status,
        );
      }

      assertConsoleClean(gate);
    });
  });
}
