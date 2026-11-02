/**
 * VIEWS-1a — view presets, ?view= contract, no rent in any view.
 * Validator tests use synthetic presets; T1 pins the shipped list.
 * Run: npm run test:map-views
 */
import assert from "node:assert/strict";
import { register } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

await register(pathToFileURL(join(here, "ts-specifier-hook.mjs")).href, {
  parentURL: import.meta.url,
});

const views = await import(pathToFileURL(join(frontendRoot, "lib/mapViews.ts")).href);
const reg = await import(pathToFileURL(join(frontendRoot, "lib/mapLayerRegistry.ts")).href);
const url = await import(pathToFileURL(join(frontendRoot, "lib/mapUrlState.ts")).href);
const groups = await import(pathToFileURL(join(frontendRoot, "lib/mapLayerGroups.ts")).href);

const {
  MAP_VIEW_PRESETS,
  assertViewPresets,
  availableViews,
  isRentLayer,
  parseViewParam,
  viewHref,
  viewIsEstimate,
  viewLayerIds,
  viewMatchesLayers,
} = views;
const { MAP_LAYER_REGISTRY, getMapLayer } = reg;
const { readMapUrlState, writeMapUrlSearch } = url;

let n = 0;
const t = (name, fn) => {
  fn();
  n += 1;
};

/** Synthetic presets (not shipped): live layers, neutral copy. */
const SYN_A = {
  id: "syn-a",
  title: "Synthetic A",
  surface: "access_services",
  overlays: ["councils"],
  finding: "Synthetic areas differ from one another.",
  sourceLine: "Synthetic Source, 2026",
  doesNotShow: "anything real.",
};
const SYN_B = { ...SYN_A, id: "syn-b", title: "Synthetic B", surface: "designations", overlays: ["4"] };
const SYN = [SYN_A, SYN_B];
const BANNED_PHRASE = /value comes from location/i;

// T1 shipped presets are valid and exact: one view only.
t("T1", () => {
  assertViewPresets();
  assert.deepEqual(
    MAP_VIEW_PRESETS.map((v) => ({ ...v, overlays: [...v.overlays] })),
    [
      {
        id: "access-to-services",
        title: "Access to services",
        surface: "access_services",
        overlays: ["councils"],
        finding:
          "Travel times to a GP, shops, schools and a post office vary widely between Scotland's local areas.",
        sourceLine: "Scottish Government SIMD, 2020; OS Boundary-Line, 2026",
        doesNotShow: "land values, or travel times from any single home.",
      },
    ],
  );
});

// T2 exact UI strings (Wording & UX signed, 2 Nov 2026).
t("T2", () => {
  assert.equal(views.VIEWS_HEADING, "Views");
  assert.equal(views.VIEWS_INTRO, "Choose a view to see one pattern on the map.");
  assert.equal(views.VIEW_DOES_NOT_SHOW_PREFIX, "What this doesn't show: ");
  assert.equal(views.VIEW_SHARE_LABEL, "Share this view");
  assert.equal(views.VIEW_SHARE_COPIED_LABEL, "Copied");
  assert.equal(views.VIEW_CLOSE_LABEL, "Close view");
  assert.equal(views.VIEW_ESTIMATE_BADGE, "Estimate");
  assert.equal(views.ALL_LAYERS_HEADING, "All layers");
  assert.equal(views.MAX_VIEW_OVERLAYS, 2);
  for (const [k, v] of Object.entries(views)) {
    if (typeof v === "string") assert.doesNotMatch(v, BANNED_PHRASE, k);
  }
});

// T3 no shipped view uses a rent layer; every rent-detector branch.
t("T3", () => {
  const rentIds = MAP_LAYER_REGISTRY.filter(isRentLayer).map((e) => e.id);
  assert.deepEqual(rentIds, ["1"]);
  assert.equal(isRentLayer(getMapLayer("agr")), true);
  const stub = { id: "x", label: "Seabed", aliases: [], legendUnit: undefined };
  assert.equal(isRentLayer(stub), false);
  assert.equal(isRentLayer({ ...stub, id: "1" }), true);
  assert.equal(isRentLayer({ ...stub, aliases: ["agr"] }), true);
  assert.equal(isRentLayer({ ...stub, label: "Land rent bands" }), true);
  assert.equal(isRentLayer({ ...stub, legendUnit: "\u00a3 per m\u00b2" }), true);
  for (const v of MAP_VIEW_PRESETS) {
    for (const id of viewLayerIds(v)) {
      assert.equal(rentIds.includes(id), false, `${v.id} uses rent layer ${id}`);
      assert.equal(isRentLayer(getMapLayer(id)), false);
    }
    const text = JSON.stringify(v);
    assert.doesNotMatch(text, /\u00a3|rent|ground/i, `${v.id} mentions rent or money`);
    assert.doesNotMatch(text, /neighbou?rhood/i, `${v.id} uses a banned word`);
    assert.doesNotMatch(text, BANNED_PHRASE, `${v.id} uses a banned phrase`);
  }
});

// T4 validator failures on synthetic presets (exact messages).
const bad = (patch, msg) =>
  assert.throws(
    () => assertViewPresets([{ ...SYN_A, ...patch }]),
    (e) => e instanceof Error && e.message === msg,
  );
t("T4", () => {
  assertViewPresets(SYN);
  assert.throws(() => assertViewPresets([]), { message: "VIEWS: presets must be a non-empty array" });
  bad({ surface: "1" }, "VIEWS: syn-a: layer '1' is a rent layer");
  bad({ overlays: ["1"] }, "VIEWS: syn-a: layer '1' is a rent layer");
  bad({ overlays: ["9", "3", "4"] }, "VIEWS: syn-a: at most 2 overlays");
  bad({ overlays: ["access_services"] }, "VIEWS: syn-a: a layer is listed twice");
  bad({ surface: "nope" }, "VIEWS: syn-a: unknown layer 'nope'");
  bad({ overlays: ["vdl"] }, "VIEWS: syn-a: layer 'vdl' is not live");
  bad({ id: "Syn A" }, "VIEWS: Syn A: id must be a lower-case slug");
  bad({ finding: "" }, "VIEWS: syn-a: finding must be non-empty");
  bad({ title: "  " }, "VIEWS: syn-a: title must be non-empty");
  bad({ doesNotShow: "the \u00a3 value." }, "VIEWS: syn-a: doesNotShow must not contain a pound sign");
  bad({ finding: "Areas differ. Towns differ." }, "VIEWS: syn-a: finding must be one sentence ending in a full stop");
  bad({ finding: "Areas differ" }, "VIEWS: syn-a: finding must be one sentence ending in a full stop");
  bad({ finding: "Areas cover 40 sites." }, "VIEWS: syn-a: finding must not contain figures");
  for (const w of ["because", "causes", "due to", "leads to", "drives", "results in", "therefore", "worked hardest"]) {
    bad({ finding: `Land differs ${w} location.` }, "VIEWS: syn-a: finding must not make a causal claim");
  }
  bad({ sourceLine: "Synthetic Source" }, "VIEWS: syn-a: sourceLine must read 'Source, year'");
  bad({ sourceLine: "Synthetic Source · 2026" }, "VIEWS: syn-a: sourceLine must read 'Source, year'");
  bad({ sourceLine: "A, 2026, B, 2026" }, "VIEWS: syn-a: sourceLine must read 'Source, year'");
  assert.throws(() => assertViewPresets([SYN_A, { ...SYN_A }]), { message: "VIEWS: syn-a: duplicate id" });
});

// T5 ?view= parsing: blank, unknown, repeated, case and whitespace.
t("T5", () => {
  assert.equal(parseViewParam(null), null);
  assert.equal(parseViewParam(""), null);
  assert.equal(parseViewParam("   "), null);
  assert.equal(parseViewParam("nope"), null);
  assert.equal(parseViewParam([]), null);
  assert.equal(parseViewParam(" Access-To-Services ")?.id, "access-to-services");
  assert.equal(parseViewParam(" SYN-B ", SYN)?.id, "syn-b");
  assert.equal(parseViewParam(["nope", "syn-a"], SYN), null);
  assert.equal(parseViewParam(["syn-b", "syn-a"], SYN)?.id, "syn-b");
  assert.equal(parseViewParam("shared-wealth"), null);
  assert.equal(readMapUrlState("").view, null);
  assert.equal(readMapUrlState("?view=").view, null);
  assert.equal(readMapUrlState("?view=%20").view, null);
  assert.equal(readMapUrlState("?view=agr").view, null);
  assert.equal(readMapUrlState("?view=1").view, null);
  assert.equal(readMapUrlState("?view=nope&layers=4").view, null);
  assert.deepEqual(readMapUrlState("?view=nope&layers=4").layers, ["4"]);
  assert.equal(readMapUrlState("?view=access-to-services").view, "access-to-services");
  assert.equal(readMapUrlState("?view=nope&view=access-to-services").view, null);
  assert.equal(readMapUrlState("?view=access-to-services&view=nope").view, "access-to-services");
  assert.equal("view" in readMapUrlState("?view=nope").unknown, false);
});

// T6 round trip through writeMapUrlSearch; unknown values never written.
t("T6", () => {
  const href = "http://local/map?layers=access_services,councils&keep=1";
  const s = writeMapUrlSearch({ href, view: "access-to-services" });
  assert.equal(s, "?layers=access_services%2Ccouncils&view=access-to-services&keep=1");
  const back = readMapUrlState(s);
  assert.equal(back.view, "access-to-services");
  assert.deepEqual(back.layers, ["access_services", "councils"]);
  assert.equal(writeMapUrlSearch({ href: `http://local/map${s}` }), s);
  assert.equal(writeMapUrlSearch({ href, view: "nope" }), "?layers=access_services%2Ccouncils&keep=1");
  assert.equal(writeMapUrlSearch({ href: `http://local/map${s}`, view: null }), "?layers=access_services%2Ccouncils&keep=1");
  assert.equal(writeMapUrlSearch({ href: "http://local/map?view=nope&layers=4" }), "?layers=4");
  assert.equal(viewHref(MAP_VIEW_PRESETS[0]), "/map?view=access-to-services");
});

// T7 matching, availability and the Estimate badge rule.
t("T7", () => {
  assert.equal(viewMatchesLayers(SYN_A, ["councils", "access_services"]), true);
  assert.equal(viewMatchesLayers(SYN_A, ["access_services"]), false);
  assert.equal(viewMatchesLayers(SYN_A, ["access_services", "councils", "4"]), false);
  assert.deepEqual(availableViews(new Set(), SYN).map((v) => v.id), ["syn-a", "syn-b"]);
  assert.deepEqual(availableViews(new Set(["4"]), SYN).map((v) => v.id), ["syn-a"]);
  assert.deepEqual(availableViews(new Set(["councils"]), SYN).map((v) => v.id), ["syn-b"]);
  assert.deepEqual(availableViews(new Set(["access_services"])).map((v) => v.id), []);
  const fake = (id) => ({ ...getMapLayer(id), sourceCaption: id === "4" ? "Scot-LAND model · 2023" : "x" });
  assert.equal(viewIsEstimate(SYN_B, fake), true);
  assert.equal(viewIsEstimate(SYN_A, fake), false);
});

// T8 'coming' layers never reach the Layers card, and none is in a view.
t("T8", () => {
  const coming = MAP_LAYER_REGISTRY.filter((e) => e.coming).map((e) => e.id);
  assert.deepEqual(coming, ["flood", "vdl", "8", "deprivation", "conservation", "listed", "stops"]);
  const listed = groups.mapDrawerLayersByGroup().flatMap((g) => g.layers.map((l) => l.id));
  for (const id of coming) assert.equal(listed.includes(id), false, `${id} listed`);
  for (const v of MAP_VIEW_PRESETS) {
    for (const id of viewLayerIds(v)) assert.equal(coming.includes(id), false);
  }
});

// T9 no shipped view carries the Estimate badge (none uses a Scot-LAND estimate).
t("T9", () => {
  assert.ok(MAP_VIEW_PRESETS.length > 0);
  for (const v of MAP_VIEW_PRESETS) {
    assert.equal(viewIsEstimate(v), false, `${v.id} would show Estimate`);
    for (const id of viewLayerIds(v)) {
      assert.equal(getMapLayer(id).sourceCaption.startsWith("Scot-LAND"), false);
    }
  }
});

console.log(`test-map-views: ${n} groups passed`);
