/** Shared top nav destinations (site rewrite PR1 — spec items 6, 13). */

export const SITE_NAV_ITEMS = [
  { id: "map", href: "/", label: "Map" },
  { id: "about", href: "/about", label: "About" },
  { id: "how", href: "/methodology", label: "How it works" },
  { id: "data", href: "/data", label: "Data & sources" },
  { id: "developers", href: "/developers", label: "Get the data" },
] as const;

export type SiteNavId = (typeof SITE_NAV_ITEMS)[number]["id"];

/** Exact research-estimate banner (once per page). */
export const RESEARCH_BANNER_LEAD = "Research estimate.";

export const RESEARCH_BANNER_BODY =
  "Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";

export const RESEARCH_BANNER_TEXT = `${RESEARCH_BANNER_LEAD} ${RESEARCH_BANNER_BODY}`;

/**
 * Muted estimate line on the map place card when a rent figure is shown
 * (FRONTEND-BATCH-4 / MAP-HINTS-OFF-1). Tests assert this constant.
 */
export const PLACE_CARD_ESTIMATE_LINE =
  "Research estimate, not a bill or an official valuation.";

/** Map search placeholder / label / title (CARD-CLARITY-31OCT-1A). */
export const SEARCH_PLACEHOLDER = "Search a postcode, or tap the map";

/** Screen-reader hint for the map search input (visible hint removed). */
export const SEARCH_HINT_SR =
  "Type a postcode or place name, or tap the map.";
/** SW-016 collapsed strip (≤768px) — exact one-line copy including expand cue. */
export const RESEARCH_BANNER_STRIP_COLLAPSED =
  "Research estimate. Not a bill or an official valuation. More";

/** /methodology only — includes approved "experimental" sentence. */
export const METHODOLOGY_RESEARCH_BANNER_BODY =
  "Scot-LAND is experimental. Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";

export const METHODOLOGY_RESEARCH_BANNER_TEXT = `${RESEARCH_BANNER_LEAD} ${METHODOLOGY_RESEARCH_BANNER_BODY}`;
