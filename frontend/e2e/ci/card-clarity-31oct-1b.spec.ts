/**
 * CARD-CLARITY-31OCT-1B — Layers drawer & place card (PR B).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  openPlaceViaCoords,
  PLACE_FIXTURE,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import {
  LIMITS_ON_USE_LABEL,
  LIMITS_ON_USE_LAYER_IDS,
  LIMITS_ON_USE_NOTE,
} from "../../components/MapLayersDrawer";
import { AIM_TO_COVER } from "../../lib/aimToCover";
import { MAP_LAYER_REGISTRY, getMapLayer } from "../../lib/mapLayerRegistry";
import {
  NEARBY_FACT_LAYER_IDS,
  NEARBY_FACT_TEXT,
  assertNearbyLayerIdsInRegistry,
  isLiveRegistryLayer,
  placeNearbyFacts,
} from "../../lib/placeNearby";

registerOpenFreeMapFontStub();

const FRONTEND_ROOT = join(__dirname, "..", "..");

const RETIRED = [
  "Area boundaries",
  "artificial privileges",
  "Protected nature sites, flood risk and crofting change best use and add no value",
  "In a SEPA flood risk area",
  "Not in a SEPA flood risk area",
  "In a crofting area",
  "Not in a crofting area",
  "Inside a protected nature site",
  "Not in a protected nature site",
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

const PLACE_WITH_NEARBY = {
  ...PLACE_FIXTURE,
  constraints: [
    { id: "flood", label: "Flood", applies: true },
    { id: "designations", label: "Protected nature sites", applies: true },
    { id: "crofting", label: "Crofting", applies: false },
    { id: "vdl", label: "Vacant", applies: true },
    { id: "stops", label: "Stops", applies: true },
  ],
};

test("CC-B-U1 locked drawer / nearby / roadmap wording", () => {
  expect(LIMITS_ON_USE_LABEL).toBe("Limits on use");
  expect(LIMITS_ON_USE_NOTE).toBe(
    "These can limit what land is used for. They add no value and are not a rent.",
  );
  expect(NEARBY_FACT_TEXT).toEqual({
    flood: {
      yes: "Includes a SEPA flood risk area",
      no: "No SEPA flood risk area mapped here",
    },
    designations: {
      yes: "Includes a protected nature site",
      no: "No protected nature site mapped here",
    },
    crofting: {
      yes: "Includes crofting land",
      no: "No crofting land mapped here",
    },
  });
  const monopoly = AIM_TO_COVER.flatMap((g) => g.rows).find(
    (row) => row.id === "monopoly-and-other-artificial-privileges",
  );
  expect(monopoly?.name).toBe("Monopolies and other special privileges");
  expect(monopoly?.name).not.toBe("Monopoly and other artificial privileges");
  expect(getMapLayer("data_zones")?.label).toBe("Local areas (data zones)");
  expect(getMapLayer("data_zones")?.label).not.toBe("Area boundaries");
});

test("CC-B-N2 no neighbourhood in app/components/lib visitor source", () => {
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

test("CC-B-N3 retired drawer / nearby strings absent", () => {
  const hits: string[] = [];
  const drawer = readFileSync(
    join(FRONTEND_ROOT, "components/MapLayersDrawer.tsx"),
    "utf8",
  );
  if (drawer.includes("Services of nature")) {
    hits.push("MapLayersDrawer.tsx: Services of nature");
  }
  if (drawer.includes("map-layers-limits-explainer")) {
    hits.push("MapLayersDrawer.tsx: map-layers-limits-explainer");
  }
  if (drawer.includes("AimPlaceholder") || drawer.includes("placeholdersFor")) {
    hits.push("MapLayersDrawer.tsx: aim placeholders");
  }

  const roots = ["app", "components", "lib"].map((d) =>
    join(FRONTEND_ROOT, d),
  );
  for (const root of roots) {
    for (const file of listSourceFiles(root)) {
      const raw = readFileSync(file, "utf8");
      for (const old of RETIRED) {
        if (raw.includes(old)) {
          hits.push(`${relative(FRONTEND_ROOT, file)}: ${old}`);
        }
      }
    }
  }
  expect(hits).toEqual([]);
});

test("CC-B-N4 nearby facts refuse non-live / unknown answers", () => {
  assertNearbyLayerIdsInRegistry();
  for (const id of NEARBY_FACT_LAYER_IDS) {
    expect(MAP_LAYER_REGISTRY.some((e) => e.id === id)).toBe(true);
  }
  expect(() => assertNearbyLayerIdsInRegistry(["not_a_layer"])).toThrow(
    /not_a_layer/,
  );
  expect(isLiveRegistryLayer("stops")).toBe(false);
  expect(isLiveRegistryLayer("vdl")).toBe(false);
  expect(isLiveRegistryLayer("flood", { floodLoaded: false })).toBe(false);
  expect(isLiveRegistryLayer("flood", { floodLoaded: true })).toBe(true);
  expect(isLiveRegistryLayer("designations")).toBe(true);
  expect(isLiveRegistryLayer("crofting")).toBe(true);

  const facts = placeNearbyFacts(
    [
      { id: "flood", label: "Flood", applies: true },
      { id: "designations", label: "Protected nature sites", applies: true },
      { id: "crofting", label: "Crofting", applies: false },
      { id: "vdl", label: "Vacant", applies: true },
      { id: "stops", label: "Stops", applies: true },
    ],
    { floodLoaded: false },
  );
  expect(facts.map((f) => f.id)).toEqual(["designations", "crofting"]);
  expect(facts.map((f) => f.text)).toEqual([
    NEARBY_FACT_TEXT.designations.yes,
    NEARBY_FACT_TEXT.crofting.no,
  ]);
  for (const fact of facts) {
    expect(isLiveRegistryLayer(fact.id)).toBe(true);
  }

  const hiddenNull = placeNearbyFacts(
    [
      { id: "crofting", label: "Crofting", applies: null },
      { id: "designations", label: "Protected nature sites", applies: null },
    ],
    { floodLoaded: false },
  );
  expect(hiddenNull).toEqual([]);
});

test("CC-B-N5 every Limits id is a registry layer", () => {
  for (const id of LIMITS_ON_USE_LAYER_IDS) {
    expect(getMapLayer(id)?.id).toBe(id);
  }
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`CC-B-E place card ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("facts before AGR; nearby live only; no fold; one disclaimer", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { place: PLACE_WITH_NEARBY });
      await openPlaceViaCoords(page);

      const card = page.getByTestId("place-card");
      const facts = card.getByTestId("place-card-facts");
      const agr = card.getByTestId("place-card-agr-heading");
      await expect(facts).toBeVisible();
      await expect(agr).toBeVisible();
      const factsBox = await facts.boundingBox();
      const agrBox = await agr.boundingBox();
      expect(factsBox).toBeTruthy();
      expect(agrBox).toBeTruthy();
      expect(factsBox!.y + factsBox!.height).toBeLessThanOrEqual(agrBox!.y + 1);

      await expect(card.getByTestId("place-card-local-area")).toHaveText(
        "Local area (data zone): City Centre South",
      );
      await expect(card.getByTestId("place-card-local-area")).not.toContainText(
        "S01014567",
      );
      await expect(card.getByTestId("place-card-nearby-designations")).toHaveText(
        NEARBY_FACT_TEXT.designations.yes,
      );
      await expect(card.getByTestId("place-card-nearby-crofting")).toHaveText(
        NEARBY_FACT_TEXT.crofting.no,
      );
      await expect(card.getByTestId("place-card-nearby-flood")).toHaveCount(0);
      await expect(card.getByTestId("place-card-nearby-vdl")).toHaveCount(0);
      await expect(card.getByTestId("place-card-nearby").locator("li")).toHaveCount(
        2,
      );

      await expect(card.getByTestId("place-card-parts")).toHaveCount(0);
      await expect(card.getByTestId("place-card-footer")).toHaveCount(1);
      await expect(card.getByTestId("place-card-estimate-line")).toHaveCount(0);
      await expect(card).not.toContainText(/neighbou?rhood/i);
      await expect(card).not.toContainText("£");
      assertConsoleClean(gate);
    });
  });

  test.describe(`CC-B-E drawer ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("no aim rows; Limits holds designations; local areas label", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);
      await openLayers(page);
      await ensureLayersGroupOpen(page, "limits");
      await ensureLayersGroupOpen(page, "places");

      const panel = page.getByTestId("layers-panel");
      await expect(panel.locator("[data-testid^='layers-aim-']")).toHaveCount(0);
      await expect(
        page.getByTestId("map-layers-roadmap-link").getByRole("link", {
          name: "What's coming next →",
          exact: true,
        }),
      ).toHaveCount(1);
      await expect(
        page
          .getByTestId("layers-group-limits")
          .getByTestId("layer-toggle-designations"),
      ).toBeVisible();
      await expect(page.getByTestId("layers-group-note-limits")).toHaveText(
        LIMITS_ON_USE_NOTE,
      );
      await expect(
        panel.getByRole("switch", {
          name: "Local areas (data zones)",
          exact: true,
        }),
      ).toHaveCount(1);
      await expect(panel.getByText("Area boundaries", { exact: true })).toHaveCount(
        0,
      );
      await expect(panel.getByText("Services of nature", { exact: true })).toHaveCount(
        0,
      );
      await expect(panel.getByText("artificial privileges", { exact: false })).toHaveCount(
        0,
      );
      const body = await panel.innerText();
      expect(body).not.toMatch(/neighbou?rhood/i);
      assertConsoleClean(gate);
    });
  });
}
