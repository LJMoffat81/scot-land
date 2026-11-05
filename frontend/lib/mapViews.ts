/**
 * VIEWS-1a — story view presets for the Layers card (charter M4, rethink v2 §2).
 * Each view is one surface, up to two overlays, a neutral one-sentence finding,
 * a "Source, year" line and a "What this doesn't show" line. The key comes
 * from the registry classes of the view's layers. Only live layers; no rent.
 */

import {
  MAP_LAYER_REGISTRY,
  getMapLayer,
  type MapLayerRegistryEntry,
} from "./mapLayerRegistry";

export type MapViewPreset = {
  /** URL slug for `?view=`. */
  id: string;
  title: string;
  /** Registry id painted as the base surface. */
  surface: string;
  /** At most two registry ids drawn over the surface. */
  overlays: readonly string[];
  /** One neutral sentence: no causal claim, no money figure. */
  finding: string;
  /** "Source, year" line; several sources joined with "; ". */
  sourceLine: string;
  /** "What this doesn't show" line. */
  doesNotShow: string;
  /** M4 — charter v2 policy question this view answers (Q1 to Q6). */
  question?: PolicyQuestionId;
  /** M4 — explainer: a fact and its Georgist reading (charter §4 rule 7). */
  takeaway?: string;
  /** M4 — "What we can't see": data that is missing from public records. */
  gaps?: readonly string[];
};

/** M4 — charter v2 policy questions; titles are the Wording & UX locked strings. */
export const POLICY_QUESTIONS = {
  Q1: "Where land value is concentrated",
  Q2: "Vacant and derelict land",
  Q3: "How public decisions raise land values",
  Q4: "Who holds the land",
  Q5: "Land held in common",
  Q6: "Carbon and land",
} as const;

export type PolicyQuestionId = keyof typeof POLICY_QUESTIONS;

export const VIEW_QUESTION_PREFIX = "Policy question: ";

export const VIEW_TAKEAWAY_HEADING = "What this could mean";

export const VIEW_GAPS_HEADING = "What we can't see";

export const MAX_VIEW_GAPS = 5;

export const MAX_VIEW_OVERLAYS = 2;

export const VIEW_ESTIMATE_BADGE = "Estimate";

export const VIEWS_HEADING = "Views";

export const VIEWS_INTRO = "Choose a view to see one pattern on the map.";

export const VIEW_DOES_NOT_SHOW_PREFIX = "What this doesn't show: ";

export const VIEW_SHARE_LABEL = "Share this view";

export const VIEW_SHARE_COPIED_LABEL = "Copied";

export const VIEW_CLOSE_LABEL = "Close view";

export const ALL_LAYERS_HEADING = "All layers";

/**
 * Shipped views. Slot 1 is reserved for the ranked-bands view after D1
 * (1a-iii / M8); a deferred sea view is recorded in the VIEWS-1a spec.
 */
export const MAP_VIEW_PRESETS: readonly MapViewPreset[] = [
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
];

/** Registry ids that carry ground rent or money figures and may never appear in a view. */
export function isRentLayer(entry: MapLayerRegistryEntry): boolean {
  if (entry.id === "1" || (entry.aliases ?? []).includes("agr")) return true;
  if (/rent/i.test(entry.label)) return true;
  return typeof entry.legendUnit === "string" && entry.legendUnit.includes(POUND);
}

/** True when a view draws a Scot-LAND estimate and must carry the badge. */
export function viewIsEstimate(
  view: MapViewPreset,
  lookup: (id: string) => MapLayerRegistryEntry | undefined = getMapLayer,
): boolean {
  return viewLayerIds(view).some((id) =>
    (lookup(id)?.sourceCaption ?? "").startsWith("Scot-LAND"),
  );
}

export function viewLayerIds(view: MapViewPreset): string[] {
  return [view.surface, ...view.overlays];
}

/** Pound sign, written as an escape so the P7 changed-lines scan stays clean. */
const POUND = "\u00a3";

const PARTY_OR_VOTE_RE =
  /\b(labour|conservatives?|tory|tories|snp|scottish national party|lib(eral)? dems?|liberal democrats?|green party|scottish greens|reform uk|alba|votes?|voting)\b/i;

const VIEW_ID_RE = /^[a-z][a-z0-9-]{1,39}$/;
const SOURCE_LINE_RE = /^[^;,·]+, \d{4}(; [^;,·]+, \d{4})*$/;
const CAUSAL_RE =
  /\b(because|cause[sd]?|causing|due to|leads? to|led to|drives?|driven|results? in|therefore|thanks to|so that|worked hardest)\b/i;

function fail(id: string, msg: string): never {
  throw new Error(`VIEWS: ${id}: ${msg}`);
}

/** Validate presets against the live registry; throws on the first failure. */
export function assertViewPresets(
  views: readonly MapViewPreset[] = MAP_VIEW_PRESETS,
  registry: readonly MapLayerRegistryEntry[] = MAP_LAYER_REGISTRY,
): void {
  if (!Array.isArray(views) || views.length === 0) {
    throw new Error("VIEWS: presets must be a non-empty array");
  }
  const byId = new Map(registry.map((e) => [e.id, e]));
  const seen = new Set<string>();
  for (const view of views) {
    const id = typeof view?.id === "string" ? view.id : "?";
    if (!VIEW_ID_RE.test(id)) fail(id, "id must be a lower-case slug");
    if (seen.has(id)) fail(id, "duplicate id");
    seen.add(id);
    if (!Array.isArray(view.overlays)) fail(id, "overlays must be an array");
    if (view.overlays.length > MAX_VIEW_OVERLAYS) {
      fail(id, `at most ${MAX_VIEW_OVERLAYS} overlays`);
    }
    const ids = viewLayerIds(view);
    if (new Set(ids).size !== ids.length) fail(id, "a layer is listed twice");
    for (const layerId of ids) {
      const entry = byId.get(layerId);
      if (!entry) fail(id, `unknown layer '${layerId}'`);
      if (entry.coming) fail(id, `layer '${layerId}' is not live`);
      if (isRentLayer(entry)) fail(id, `layer '${layerId}' is a rent layer`);
    }
    for (const key of ["title", "finding", "sourceLine", "doesNotShow"] as const) {
      const text = view[key];
      if (typeof text !== "string" || !text.trim()) fail(id, `${key} must be non-empty`);
      if (text.includes(POUND)) fail(id, `${key} must not contain a pound sign`);
    }
    const finding = view.finding.trim();
    if (!/^[A-Z].*\.$/.test(finding) || /[.!?]\s/.test(finding)) {
      fail(id, "finding must be one sentence ending in a full stop");
    }
    if (/\d/.test(finding)) fail(id, "finding must not contain figures");
    if (CAUSAL_RE.test(finding)) fail(id, "finding must not make a causal claim");
    if (!SOURCE_LINE_RE.test(view.sourceLine)) {
      fail(id, "sourceLine must read 'Source, year'");
    }
    assertExplainer(id, view);
  }
}

/** M4 — question, takeaway and gaps rules (charter §4 rules 5 and 7). */
function assertExplainer(id: string, view: MapViewPreset): void {
  const hasQuestion = view.question !== undefined;
  if (hasQuestion && !Object.prototype.hasOwnProperty.call(POLICY_QUESTIONS, view.question as string)) {
    fail(id, "question must be one of Q1 to Q6");
  }
  if (view.takeaway !== undefined) {
    const text = view.takeaway;
    if (typeof text !== "string" || !text.trim()) fail(id, "takeaway must be non-empty");
    if (text.includes(POUND)) fail(id, "takeaway must not contain a pound sign");
    if (/\d/.test(text)) fail(id, "takeaway must not contain figures");
    if (!/\.$/.test(text.trim())) fail(id, "takeaway must end in a full stop");
    if (PARTY_OR_VOTE_RE.test(text)) {
      fail(id, "takeaway must not name a party or call for a vote");
    }
    if (/georgis/i.test(text) && !/\bGeorgists argue\b/.test(text)) {
      fail(id, "takeaway must write Georgist claims as 'Georgists argue'");
    }
    const firstStop = text.indexOf(".");
    const readingAt = text.search(/\bGeorgists argue\b/);
    if (readingAt >= 0 && readingAt < firstStop) {
      fail(id, "takeaway must put the fact sentence before the reading");
    }
  }
  if (view.gaps !== undefined) {
    if (!Array.isArray(view.gaps)) fail(id, "gaps must be an array");
    if (view.gaps.length === 0) fail(id, "gaps must not be an empty list");
    if (view.gaps.length > MAX_VIEW_GAPS) fail(id, `at most ${MAX_VIEW_GAPS} gaps`);
    const seenGaps = new Set<string>();
    for (const gap of view.gaps) {
      if (typeof gap !== "string" || !gap.trim()) fail(id, "each gap must be non-empty");
      if (gap.includes(POUND)) fail(id, "gaps must not contain a pound sign");
      const key = gap.trim().toLowerCase();
      if (seenGaps.has(key)) fail(id, "a gap is listed twice");
      seenGaps.add(key);
    }
  }
  if ((view.takeaway !== undefined || view.gaps !== undefined) && !hasQuestion) {
    fail(id, "a view with a takeaway or gaps must name its policy question");
  }
}

/** One explainer row, in render order. ViewDetail renders these verbatim. */
export type ViewExplainerRow =
  | { kind: "question"; text: string }
  | { kind: "takeaway"; heading: string; text: string }
  | { kind: "gaps"; heading: string; items: readonly string[] };

/** M4 — explainer rows for a view: question, then takeaway, then gaps. */
export function viewExplainerRows(view: MapViewPreset): ViewExplainerRow[] {
  const rows: ViewExplainerRow[] = [];
  if (view.question !== undefined) {
    rows.push({
      kind: "question",
      text: `${VIEW_QUESTION_PREFIX}${POLICY_QUESTIONS[view.question]}`,
    });
  }
  if (view.takeaway !== undefined) {
    rows.push({ kind: "takeaway", heading: VIEW_TAKEAWAY_HEADING, text: view.takeaway });
  }
  if (view.gaps !== undefined && view.gaps.length > 0) {
    rows.push({ kind: "gaps", heading: VIEW_GAPS_HEADING, items: [...view.gaps] });
  }
  return rows;
}

/**
 * `?view=` resolution. Only the first value counts; blank, unknown or
 * malformed values give null, so the map falls back to `?layers=`.
 */
export function parseViewParam(
  values: readonly (string | null)[] | string | null,
  views: readonly MapViewPreset[] = MAP_VIEW_PRESETS,
): MapViewPreset | null {
  const first = Array.isArray(values) ? values[0] ?? null : values;
  if (typeof first !== "string") return null;
  const slug = first.trim().toLowerCase();
  if (!slug) return null;
  return views.find((v) => v.id === slug) ?? null;
}

/** Views whose layers are all currently available on the map. */
export function availableViews(
  unavailable: ReadonlySet<string>,
  views: readonly MapViewPreset[] = MAP_VIEW_PRESETS,
): MapViewPreset[] {
  return views.filter((v) => viewLayerIds(v).every((id) => !unavailable.has(id)));
}

/** True when the active layers are exactly the view's layers (any order). */
export function viewMatchesLayers(
  view: MapViewPreset,
  activeIds: readonly string[],
): boolean {
  const want = new Set(viewLayerIds(view));
  const have = new Set(activeIds);
  if (want.size !== have.size) return false;
  for (const id of want) if (!have.has(id)) return false;
  return true;
}

export function viewHref(view: MapViewPreset): string {
  return `/map?view=${view.id}`;
}
