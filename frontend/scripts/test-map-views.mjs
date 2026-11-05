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
const whoHolds = await import(pathToFileURL(join(frontendRoot, "lib/whoHolds.ts")).href);
const idleLand = await import(pathToFileURL(join(frontendRoot, "lib/idleLand.ts")).href);
const reg = await import(pathToFileURL(join(frontendRoot, "lib/mapLayerRegistry.ts")).href);
const legend = await import(pathToFileURL(join(frontendRoot, "lib/landWorthCividis.mjs")).href);
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

// T1 shipped presets are valid and exact (access-to-services plus M5).
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
      {
        id: "who-holds-scotland",
        title: "Who holds Scotland",
        surface: "who_holds",
        overlays: ["councils"],
        finding:
          "Community-owned land is recorded by council in the official Scottish Government survey.",
        sourceLine:
          "Scottish Government, Community Ownership in Scotland 2024 (published November 2025); OS Boundary-Line, 2026",
        doesNotShow: "named owners, holdings below council level, or a map of legal title.",
        question: "Q4",
        takeaway:
          "Public records show community-owned land by council, and they do not say who holds most of the rest of Scotland's title. Georgists argue that whoever holds that title collects what the land itself earns.",
        gaps: [
          "Large land holdings of 1,000 hectares or more: no official open dataset exists, and the Land Reform (Scotland) Act 2025 duties are not in force.",
          "A complete picture of who holds title: the Land Register is not finished, and Registers of Scotland INSPIRE parcels carry no owner names.",
          "Public sector and Crown land: no verified open dataset is published.",
          "Crofting map extents: the Crofting Commission publishes lists, but the map polygons are not openly redistributable.",
          "Some community-owned assets have no published area.",
        ],
      },
      {
        id: "idle-land",
        title: "Vacant and derelict land",
        surface: "idle_land",
        overlays: ["councils"],
        finding:
          "Vacant and derelict land is recorded by council in the official Scottish Government survey.",
        sourceLine:
          "Scottish Government, Scottish Vacant and Derelict Land Survey 2025 (published September 2026); OS Boundary-Line, 2026",
        doesNotShow: "named owners, housing land supply, or a map of legal title.",
        question: "Q2",
        takeaway:
          "This land is recorded as vacant or derelict in the official survey. The Scottish Land Commission has asked whether tax could help bring such land back into use.",
        gaps: [
          "Housing land supply: no public map until the Improvement Service confirms the records can be shared.",
          "A site-by-site picture of who holds vacant or derelict land: this view does not show owners.",
          "Years recorded derelict on the map: the survey records when each site was first identified, but this view does not colour long-term derelict land separately.",
          "Loch Lomond and the Trossachs National Park: seven sites and seven hectares sit outside the 32 council totals.",
          "Five councils sent no 2025 return, so their latest figures are shown: 2022 for Orkney Islands, and 2024 for Clackmannanshire, Falkirk, Inverclyde and West Lothian.",
        ],
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
  assert.deepEqual(availableViews(new Set(["access_services"])).map((v) => v.id), ["who-holds-scotland", "idle-land"]);
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

// ---- M4 story-view framework: question, takeaway ("What this could mean"), gaps ----
const SYN_Q = {
  ...SYN_A,
  id: "syn-q",
  question: "Q4",
  takeaway: "A synthetic fact holds. Georgists argue that a synthetic reading follows.",
  gaps: ["Synthetic gap one.", "Synthetic gap two."],
};

// T10 exact M4 strings (Wording & UX locked) and policy-question titles.
t("T10", () => {
  assert.equal(views.VIEW_QUESTION_PREFIX, "Policy question: ");
  assert.equal(views.VIEW_TAKEAWAY_HEADING, "What this could mean");
  assert.equal(views.VIEW_GAPS_HEADING, "What we can't see");
  assert.equal(views.MAX_VIEW_GAPS, 5);
  assert.deepEqual(views.POLICY_QUESTIONS, {
    Q1: "Where land value is concentrated",
    Q2: "Vacant and derelict land",
    Q3: "How public decisions raise land values",
    Q4: "Who holds the land",
    Q5: "Land held in common",
    Q6: "Carbon and land",
  });
});

// T11 every explainer rule fails with its exact message, one trigger at a time.
t("T11", () => {
  assertViewPresets([SYN_Q], MAP_LAYER_REGISTRY);
  const bad = (patch, msg) => {
    const v = { ...SYN_Q, ...patch };
    for (const k of Object.keys(patch)) if (patch[k] === undefined) delete v[k];
    assert.throws(() => assertViewPresets([v], MAP_LAYER_REGISTRY), {
      message: `VIEWS: syn-q: ${msg}`,
    });
  };
  bad({ question: "Q7" }, "question must be one of Q1 to Q6");
  bad({ question: "q4" }, "question must be one of Q1 to Q6");
  bad({ question: "toString" }, "question must be one of Q1 to Q6");
  bad({ takeaway: "   " }, "takeaway must be non-empty");
  bad({ takeaway: "Synthetic land costs \u00a3 here." }, "takeaway must not contain a pound sign");
  bad({ takeaway: "Synthetic land is held by few owners in 2026." }, "takeaway must not contain figures");
  bad({ takeaway: "Synthetic land is held by few owners" }, "takeaway must end in a full stop");
  for (const word of ["Labour", "the SNP", "Scottish Greens", "Reform UK", "vote", "voting"]) {
    bad({ takeaway: `Synthetic owners and ${word} differ.` }, "takeaway must not name a party or call for a vote");
  }
  bad({ takeaway: "Georgism says synthetic land is unearned." }, "takeaway must write Georgist claims as 'Georgists argue'");
  bad({ takeaway: "Georgists claim synthetic land is unearned." }, "takeaway must write Georgist claims as 'Georgists argue'");
  bad({ takeaway: "Georgists argue that a synthetic reading follows. A synthetic fact holds." }, "takeaway must put the fact sentence before the reading");
  bad({ gaps: "Synthetic gap." }, "gaps must be an array");
  bad({ gaps: [] }, "gaps must not be an empty list");
  bad({ gaps: ["a.", "b.", "c.", "d.", "e.", "f."] }, "at most 5 gaps");
  bad({ gaps: ["Synthetic gap.", " "] }, "each gap must be non-empty");
  bad({ gaps: ["Synthetic \u00a3 gap."] }, "gaps must not contain a pound sign");
  bad({ gaps: ["Synthetic gap.", " synthetic GAP. "] }, "a gap is listed twice");
  bad({ question: undefined }, "a view with a takeaway or gaps must name its policy question");
  bad({ question: undefined, gaps: undefined }, "a view with a takeaway or gaps must name its policy question");
  bad({ question: undefined, takeaway: undefined }, "a view with a takeaway or gaps must name its policy question");
  // Not over-broad: a question alone, five gaps, and ordinary words pass.
  assertViewPresets([{ ...SYN_A, id: "syn-q", question: "Q1" }], MAP_LAYER_REGISTRY);
  assertViewPresets([{ ...SYN_Q, gaps: ["a.", "b.", "c.", "d.", "e."] }], MAP_LAYER_REGISTRY);
  assertViewPresets(
    [{ ...SYN_Q, takeaway: "Synthetic labourers and devoted greens differ across the reformed alban areas." }],
    MAP_LAYER_REGISTRY,
  );
});

// T12 explainer rows: exact order and text; absent fields give no row.
t("T12", () => {
  assert.deepEqual(views.viewExplainerRows(SYN_Q), [
    { kind: "question", text: "Policy question: Who holds the land" },
    {
      kind: "takeaway",
      heading: "What this could mean",
      text: "A synthetic fact holds. Georgists argue that a synthetic reading follows.",
    },
    { kind: "gaps", heading: "What we can't see", items: ["Synthetic gap one.", "Synthetic gap two."] },
  ]);
  assert.deepEqual(views.viewExplainerRows(SYN_A), []);
  assert.deepEqual(views.viewExplainerRows({ ...SYN_A, question: "Q5" }), [
    { kind: "question", text: "Policy question: Land held in common" },
  ]);
  // Takeaway sentence order: fact first, then the reading (Wording & UX lock).
  const takeaway = SYN_Q.takeaway;
  const firstStop = takeaway.indexOf(".");
  assert.ok(firstStop > 0 && !/\bGeorgists argue\b/.test(takeaway.slice(0, firstStop)));
  assert.match(takeaway.slice(firstStop), /\bGeorgists argue\b/);
});

// T13 M5 is the first shipped view with explainer fields; others stay unset.
t("T13", () => {
  const m5 = MAP_VIEW_PRESETS.find((v) => v.id === "who-holds-scotland");
  assert.ok(m5, "who-holds-scotland missing");
  assert.equal(m5.question, "Q4");
  assert.equal(m5.surface, "who_holds");
  assert.deepEqual(views.viewExplainerRows(m5), [
    { kind: "question", text: "Policy question: Who holds the land" },
    {
      kind: "takeaway",
      heading: "What this could mean",
      text: m5.takeaway,
    },
    { kind: "gaps", heading: "What we can't see", items: [...m5.gaps] },
  ]);
  const firstStop = m5.takeaway.indexOf(".");
  assert.ok(firstStop > 0 && !/\bGeorgists argue\b/.test(m5.takeaway.slice(0, firstStop)));
  assert.match(m5.takeaway.slice(firstStop), /\bGeorgists argue\b/);
  const m2 = MAP_VIEW_PRESETS.find((v) => v.id === "idle-land");
  assert.ok(m2, "idle-land missing");
  assert.equal(m2.question, "Q2");
  assert.equal(m2.surface, "idle_land");
  assert.deepEqual(views.viewExplainerRows(m2), [
    { kind: "question", text: "Policy question: Vacant and derelict land" },
    {
      kind: "takeaway",
      heading: "What this could mean",
      text: m2.takeaway,
    },
    { kind: "gaps", heading: "What we can't see", items: [...m2.gaps] },
  ]);
  const m2First = m2.takeaway.indexOf(".");
  assert.ok(m2First > 0);
  assert.equal(
    m2.takeaway.slice(0, m2First + 1),
    "This land is recorded as vacant or derelict in the official survey.",
  );
  assert.match(
    m2.takeaway.slice(m2First),
    /The Scottish Land Commission has asked whether tax could help bring such land back into use\./,
  );
  for (const v of MAP_VIEW_PRESETS) {
    if (v.id === "who-holds-scotland" || v.id === "idle-land") continue;
    assert.equal(v.question, undefined, `${v.id} question`);
    assert.equal(v.takeaway, undefined, `${v.id} takeaway`);
    assert.equal(v.gaps, undefined, `${v.id} gaps`);
    assert.deepEqual(views.viewExplainerRows(v), []);
  }
});


// T14 M5 payload parser: isolated refusals, exact messages; synthetic fixtures only.
t("T14", () => {
  const { parseWhoHoldsPayload, WhoHoldsRefused, syntheticWhoHoldsPayload, WHO_HOLDS_BANDS } = whoHolds;
  const ok = () => parseWhoHoldsPayload(syntheticWhoHoldsPayload());
  ok();
  const bad = (raw, reason) => {
    assert.throws(() => parseWhoHoldsPayload(raw), (e) => {
      return e instanceof WhoHoldsRefused && e.message === `WHO-HOLDS: REFUSED: ${reason}`;
    });
  };
  bad([], "payload: expected object");
  bad(syntheticWhoHoldsPayload({ vintage: "2024\u00a3" }), "payload contains a pound sign");
  const gbp = syntheticWhoHoldsPayload();
  gbp.source = { ...gbp.source, licence: "Open Government Licence with GBP note" };
  bad(gbp, "payload contains a pound sign");
  bad(syntheticWhoHoldsPayload({ group_name: "Trust" }), "extract must not contain owner names");
  bad(syntheticWhoHoldsPayload({ extra: 1 }), "payload keys do not match contract");
  const noCouncils = syntheticWhoHoldsPayload();
  delete noCouncils.councils;
  bad(noCouncils, "payload keys do not match contract");
  bad(syntheticWhoHoldsPayload({ layer_id: "community_ownership" }), "layer_id: expected who_holds");
  bad(syntheticWhoHoldsPayload({ level: "data_zone" }), "level: expected council");
  bad(syntheticWhoHoldsPayload({ vintage: "2025" }), "vintage: expected 2024");
  const src = syntheticWhoHoldsPayload();
  src.source = { ...src.source, note: "x" };
  bad(src, "source keys do not match contract");
  const empty = syntheticWhoHoldsPayload({ councils: [] });
  bad(empty, "councils: expected 32 councils");
  const one = syntheticWhoHoldsPayload();
  one.councils = [one.councils[0]];
  bad(one, "councils: expected 32 councils");
  const named = syntheticWhoHoldsPayload();
  named.councils = named.councils.map((row, i) => (i === 0 ? { ...row, postcode: "EH1 1YZ" } : row));
  bad(named, "extract must not contain owner names");
  const extraRow = syntheticWhoHoldsPayload();
  extraRow.councils = extraRow.councils.map((row, i) => (i === 0 ? { ...row, owner: "A" } : row));
  bad(extraRow, "extract must not contain owner names");
  const badCode = syntheticWhoHoldsPayload();
  badCode.councils = badCode.councils.map((row, i) => (i === 0 ? { ...row, code: "E12000001" } : row));
  bad(badCode, "council code: expected official council");
  const dup = syntheticWhoHoldsPayload();
  dup.councils = dup.councils.map((row, i) => (i === 1 ? { ...row, code: dup.councils[0].code } : row));
  bad(dup, `council ${dup.councils[0].code}: listed twice`);
  const band = syntheticWhoHoldsPayload();
  band.councils = band.councils.map((row, i) => (i === 0 ? { ...row, band: "secret" } : row));
  bad(band, `council ${band.councils[0].code}: unknown band`);
  assert.equal(WHO_HOLDS_BANDS.length, 4);
});

// T15 M5 hectare display and cividis steps (imported ramp, not a hard-coded copy).
t("T15", () => {
  const {
    formatWhoHoldsHectares,
    whoHoldsCividisColors,
    WHO_HOLDS_BANDS,
    WHO_HOLDS_HA_LESS_THAN_ONE,
  } = whoHolds;
  assert.equal(formatWhoHoldsHectares(0), "0");
  assert.equal(formatWhoHoldsHectares(0.4), WHO_HOLDS_HA_LESS_THAN_ONE);
  assert.equal(formatWhoHoldsHectares(0.49), WHO_HOLDS_HA_LESS_THAN_ONE);
  assert.equal(formatWhoHoldsHectares(0.5), "1");
  assert.equal(formatWhoHoldsHectares(1), "1");
  assert.equal(formatWhoHoldsHectares(1234.6), "1,235");
  assert.equal(formatWhoHoldsHectares(999.5), "1,000");
  assert.equal(formatWhoHoldsHectares(1000), "1,000");
  assert.equal(WHO_HOLDS_HA_LESS_THAN_ONE, "Less than 1");
  const colors = whoHoldsCividisColors();
  assert.equal(colors.length, 4);
  assert.equal(colors[0], legend.LAND_WORTH_CIVIDIS[legend.LAND_WORTH_CIVIDIS.length - 1]);
  assert.equal(colors[3], legend.LAND_WORTH_CIVIDIS[0]);
  const last = legend.LAND_WORTH_CIVIDIS.length - 1;
  const expected = [0, 1, 2, 3].map(
    (i) => legend.LAND_WORTH_CIVIDIS[last - Math.round((i * last) / 3)],
  );
  assert.deepEqual(colors, expected);
  assert.deepEqual(WHO_HOLDS_BANDS.map((b) => b.color), expected);
  const whoHoldsLayer = reg.MAP_LAYER_REGISTRY.find((e) => e.id === "who_holds");
  assert.deepEqual(
    whoHoldsLayer.classes.map((c) => c.color),
    expected,
  );
});

// T16 M2 payload parser: isolated refusals, exact messages; synthetic fixtures only.
t("T16", () => {
  const { parseIdleLandPayload, IdleLandRefused, syntheticIdleLandPayload, IDLE_LAND_BANDS } = idleLand;
  const ok = () => parseIdleLandPayload(syntheticIdleLandPayload());
  ok();
  const bad = (raw, reason) => {
    assert.throws(() => parseIdleLandPayload(raw), (e) => {
      return e instanceof IdleLandRefused && e.message === `IDLE-LAND: REFUSED: ${reason}`;
    });
  };
  bad([], "payload: expected object");
  bad(syntheticIdleLandPayload({ vintage: "2025\u00a3" }), "payload contains a pound sign");
  const gbp = syntheticIdleLandPayload();
  gbp.source = { ...gbp.source, licence: "Open Government Licence with GBP note" };
  bad(gbp, "payload contains a pound sign");
  bad(syntheticIdleLandPayload({ group_name: "Trust" }), "extract must not contain owner names");
  bad(syntheticIdleLandPayload({ extra: 1 }), "payload keys do not match contract");
  const noCouncils = syntheticIdleLandPayload();
  delete noCouncils.councils;
  bad(noCouncils, "payload keys do not match contract");
  bad(syntheticIdleLandPayload({ layer_id: "vdl" }), "layer_id: expected idle_land");
  bad(syntheticIdleLandPayload({ level: "data_zone" }), "level: expected council");
  bad(syntheticIdleLandPayload({ vintage: "2024" }), "vintage: expected 2025");
  const src = syntheticIdleLandPayload();
  src.source = { ...src.source, note: "x" };
  bad(src, "source keys do not match contract");
  const empty = syntheticIdleLandPayload({ councils: [] });
  bad(empty, "councils: expected 32 councils");
  const one = syntheticIdleLandPayload();
  one.councils = [one.councils[0]];
  bad(one, "councils: expected 32 councils");
  const named = syntheticIdleLandPayload();
  named.councils = named.councils.map((row, i) => (i === 0 ? { ...row, postcode: "EH1 1YZ" } : row));
  bad(named, "extract must not contain owner names");
  const extraRow = syntheticIdleLandPayload();
  extraRow.councils = extraRow.councils.map((row, i) => (i === 0 ? { ...row, owner: "A" } : row));
  bad(extraRow, "extract must not contain owner names");
  const badCode = syntheticIdleLandPayload();
  badCode.councils = badCode.councils.map((row, i) => (i === 0 ? { ...row, code: "E12000001" } : row));
  bad(badCode, "council code: expected official council");
  const dup = syntheticIdleLandPayload();
  dup.councils = dup.councils.map((row, i) => (i === 1 ? { ...row, code: dup.councils[0].code } : row));
  bad(dup, `council ${dup.councils[0].code}: listed twice`);
  const band = syntheticIdleLandPayload();
  band.councils = band.councils.map((row, i) => (i === 0 ? { ...row, band: "secret" } : row));
  bad(band, `council ${band.councils[0].code}: unknown band`);
  assert.equal(IDLE_LAND_BANDS.length, 4);
});

// T17 M2 hectare display and cividis steps (imported ramp, not a hard-coded copy).
t("T17", () => {
  const {
    formatIdleLandHectares,
    idleLandCividisColors,
    IDLE_LAND_BANDS,
    IDLE_LAND_HA_LESS_THAN_ONE,
  } = idleLand;
  assert.equal(formatIdleLandHectares(0), "0");
  assert.equal(formatIdleLandHectares(0.4), IDLE_LAND_HA_LESS_THAN_ONE);
  assert.equal(formatIdleLandHectares(0.49), IDLE_LAND_HA_LESS_THAN_ONE);
  assert.equal(formatIdleLandHectares(0.5), "1");
  assert.equal(formatIdleLandHectares(1), "1");
  assert.equal(formatIdleLandHectares(1234.6), "1,235");
  assert.equal(formatIdleLandHectares(999.5), "1,000");
  assert.equal(formatIdleLandHectares(1000), "1,000");
  assert.equal(IDLE_LAND_HA_LESS_THAN_ONE, "Less than 1");
  const colors = idleLandCividisColors();
  assert.equal(colors.length, 4);
  assert.equal(colors[0], legend.LAND_WORTH_CIVIDIS[legend.LAND_WORTH_CIVIDIS.length - 1]);
  assert.equal(colors[3], legend.LAND_WORTH_CIVIDIS[0]);
  const last = legend.LAND_WORTH_CIVIDIS.length - 1;
  const expected = [0, 1, 2, 3].map(
    (i) => legend.LAND_WORTH_CIVIDIS[last - Math.round((i * last) / 3)],
  );
  assert.deepEqual(colors, expected);
  assert.deepEqual(IDLE_LAND_BANDS.map((b) => b.color), expected);
  const idleLandLayer = reg.MAP_LAYER_REGISTRY.find((e) => e.id === "idle_land");
  assert.deepEqual(
    idleLandLayer.classes.map((c) => c.color),
    expected,
  );
});

// T18 no user-facing "Idle"; S45 title and Q2 title are the same locked words.
t("T18", () => {
  const view = MAP_VIEW_PRESETS.find((v) => v.id === "idle-land");
  assert.ok(view, "idle-land missing");
  const layer = reg.MAP_LAYER_REGISTRY.find((e) => e.id === "idle_land");
  assert.ok(layer, "idle_land missing");
  const visible = [
    view.title,
    view.finding,
    view.sourceLine,
    view.doesNotShow,
    view.takeaway,
    ...(view.gaps ?? []),
    layer.label,
    layer.sourceCaption,
    ...(layer.classes ?? []).map((c) => c.label),
    idleLand.IDLE_LAND_TABLE_HEADING,
    idleLand.IDLE_LAND_COL_COUNCIL,
    idleLand.IDLE_LAND_COL_SITES,
    idleLand.IDLE_LAND_COL_HECTARES,
    idleLand.IDLE_LAND_HA_LESS_THAN_ONE,
    ...idleLand.IDLE_LAND_BANDS.map((b) => b.label),
  ];
  for (const text of visible) {
    assert.equal(typeof text, "string");
    assert.doesNotMatch(text, /Idle/, `visible string contains Idle: ${text}`);
  }
  // Honest clash: S45 and the locked Q2 title are the same words.
  // The explainer distinguishes them with VIEW_QUESTION_PREFIX, not a made-up title.
  assert.equal(view.title, "Vacant and derelict land");
  assert.equal(views.POLICY_QUESTIONS.Q2, "Vacant and derelict land");
  assert.equal(view.title, views.POLICY_QUESTIONS.Q2);
  assert.equal(layer.label, view.title);
  const question = views.viewExplainerRows(view).find((row) => row.kind === "question");
  assert.equal(question?.text, `${views.VIEW_QUESTION_PREFIX}${views.POLICY_QUESTIONS.Q2}`);
  assert.equal(question?.text, "Policy question: Vacant and derelict land");
});

console.log(`test-map-views: ${n} groups passed`);
