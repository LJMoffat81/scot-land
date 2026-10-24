/**
 * LAYERS-CARD-1 — five-group Georgist Layers card + KEY-IN-LAYERS-ONLY-1.
 * NLC-1..NLC-3 are pure; ELC-1 is Playwright at 1280×800 and 390×844.
 */
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import {
  MAP_LAYER_GROUP_NOTES,
  MAP_LAYER_GROUP_ORDER,
  MAP_LAYER_REGISTRY,
  assertRegistryZoomAndGroup,
  defaultOnLayerIds,
  mapLayerGroupLabel,
  mapLayerGroupNote,
  type MapLayerRegistryEntry,
} from "../../lib/mapLayerRegistry";
import { mapDrawerLayersByGroup } from "../../lib/mapLayerGroups";

registerOpenFreeMapFontStub();

const GROUP_NOTES = {
  land: "Land is worth what its location gives access to: homes, jobs, services and permission to build.",
  tenure: "Who holds land decides who collects its rent.",
  resources:
    "Oil, gas, seabed, wind and water are commons. Their rent belongs to everyone, not only the licence holder.",
  nature: "Estimates only. Never taxed.",
  places: "The official lines everything else is measured within.",
} as const;

test("NLC-1 five-group order, crofting in tenure, defaultOn councils", () => {
  expect([...MAP_LAYER_GROUP_ORDER]).toEqual([
    "land",
    "tenure",
    "resources",
    "nature",
    "places",
  ]);
  expect(mapLayerGroupLabel("tenure")).toBe("Who holds the land");
  expect(MAP_LAYER_GROUP_NOTES).toEqual(GROUP_NOTES);
  const crofting = MAP_LAYER_REGISTRY.find((e) => e.id === "crofting");
  expect(crofting?.group).toBe("tenure");
  const byGroup = mapDrawerLayersByGroup();
  expect(byGroup.map((g) => g.key)).toEqual([
    "land",
    "tenure",
    "resources",
    "nature",
    "places",
  ]);
  const tenureIds = byGroup
    .find((g) => g.key === "tenure")
    ?.layers.map((l) => l.id);
  expect(tenureIds).toContain("crofting");
  const natureIds = byGroup
    .find((g) => g.key === "nature")
    ?.layers.map((l) => l.id);
  expect(natureIds ?? []).not.toContain("crofting");
  expect(defaultOnLayerIds()).toEqual(["councils"]);
});

test("NLC-2a mapLayerGroupNote rejects non-string / empty group", () => {
  for (const badGroup of [
    undefined,
    null,
    "",
    "   ",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => mapLayerGroupNote(badGroup)).toThrow(
      /^LAYERS-CARD: group must be a non-empty string$/,
    );
  }
});

test("NLC-2b mapLayerGroupNote rejects unknown group", () => {
  for (const unknown of ["unknown", "sites", "boundaries", "LAND"]) {
    expect(() => mapLayerGroupNote(unknown)).toThrow(
      new RegExp(
        `^LAYERS-CARD: unknown group '${unknown.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}'$`,
      ),
    );
  }
});

test("NLC-2c mapLayerGroupNote rejects non-object notes", () => {
  for (const badNotes of [null, "str", 123, 1.5, true, false, []]) {
    expect(() => mapLayerGroupNote("land", badNotes)).toThrow(
      /^LAYERS-CARD: notes must be an object$/,
    );
  }
});

test("NLC-2d mapLayerGroupNote rejects empty / non-string note values", () => {
  for (const badVal of [
    undefined,
    null,
    "",
    "   ",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => mapLayerGroupNote("tenure", { tenure: badVal })).toThrow(
      /^LAYERS-CARD: tenure: note must be a non-empty string$/,
    );
  }
  expect(mapLayerGroupNote("tenure")).toBe(GROUP_NOTES.tenure);
});

const BASE_ENTRY: MapLayerRegistryEntry = {
  id: "x",
  group: "land",
  label: "X",
  minzoom: 0,
  maxzoom: 20,
  sourceCaption: "test",
  classes: [{ label: "a", color: "#000" }],
};

test("NLC-3a assertRegistryZoomAndGroup rejects non-numeric zoom", () => {
  for (const badMin of [
    undefined,
    null,
    "5",
    NaN,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertRegistryZoomAndGroup([
        { ...BASE_ENTRY, minzoom: badMin as number },
      ]),
    ).toThrow(/^layer x: minzoom must be numeric$/);
  }
  for (const badMax of [
    undefined,
    null,
    "5",
    NaN,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertRegistryZoomAndGroup([
        { ...BASE_ENTRY, maxzoom: badMax as number },
      ]),
    ).toThrow(/^layer x: maxzoom must be numeric$/);
  }
});

test("NLC-3b assertRegistryZoomAndGroup rejects empty / non-string group", () => {
  for (const badGroup of [
    undefined,
    null,
    "",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertRegistryZoomAndGroup([
        {
          ...BASE_ENTRY,
          group: badGroup as MapLayerRegistryEntry["group"],
        },
      ]),
    ).toThrow(/^layer x: group must be non-empty$/);
  }
});

test("NLC-3c assertRegistryZoomAndGroup rejects unknown group", () => {
  expect(() =>
    assertRegistryZoomAndGroup([
      { ...BASE_ENTRY, group: "bogus" as MapLayerRegistryEntry["group"] },
    ]),
  ).toThrow(/^LAYERS-CARD: layer x: unknown group 'bogus'$/);
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`ELC-1 LAYERS-CARD-1 (${viewport.width})`, () => {
    test.use({ viewport });

    test("five group notes, crofting in tenure, no floating keys", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);

      await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
      await expect(page.getByTestId("legend-strip")).toHaveCount(0);

      await openLayers(page);
      for (const key of [
        "land",
        "tenure",
        "resources",
        "nature",
        "places",
      ] as const) {
        await ensureLayersGroupOpen(page, key);
      }

      await expect(page.getByTestId("layers-group-note-land")).toHaveText(
        GROUP_NOTES.land,
      );
      await expect(page.getByTestId("layers-group-note-tenure")).toHaveText(
        GROUP_NOTES.tenure,
      );
      await expect(page.getByTestId("layers-group-note-resources")).toHaveText(
        GROUP_NOTES.resources,
      );
      await expect(page.getByTestId("layers-nature-note")).toHaveText(
        GROUP_NOTES.nature,
      );
      await expect(page.getByTestId("layers-group-note-places")).toHaveText(
        GROUP_NOTES.places,
      );

      await expect(
        page
          .getByTestId("layers-group-tenure")
          .getByTestId("layer-toggle-crofting"),
      ).toBeVisible();
      await expect(
        page
          .getByTestId("layers-group-nature")
          .getByTestId("layer-toggle-crofting"),
      ).toHaveCount(0);

      await page.getByTestId("layer-toggle-access_services").click();
      await expect(
        page.getByTestId("layer-inline-legend-access_services"),
      ).toBeVisible();

      await page.getByTestId("map-panel-slot-close").click();
      await expect(page.getByTestId("layers-panel")).toHaveCount(0);
      await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
      await expect(page.getByTestId("legend-strip")).toHaveCount(0);
      assertConsoleClean(gate);
    });
  });
}
