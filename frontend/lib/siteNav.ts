/** Shared top nav destinations (site rewrite PR1 — spec items 6, 13). */

export const SITE_NAV_ITEMS = [
  { id: "map", href: "/", label: "Map" },
  { id: "about", href: "/about", label: "About" },
  { id: "how", href: "/methodology", label: "How it works" },
  { id: "data", href: "/data", label: "Data & sources" },
  { id: "developers", href: "/developers", label: "Downloads & API" },
] as const;

export type SiteNavId = (typeof SITE_NAV_ITEMS)[number]["id"];

/** Exact research-estimate banner (once per page). */
export const RESEARCH_BANNER_LEAD = "Research estimate.";

export const RESEARCH_BANNER_BODY =
  "Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";

export const RESEARCH_BANNER_TEXT = `${RESEARCH_BANNER_LEAD} ${RESEARCH_BANNER_BODY}`;

/** /methodology only — includes approved "experimental" sentence. */
export const METHODOLOGY_RESEARCH_BANNER_BODY =
  "Scot-LAND is experimental. Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";

export const METHODOLOGY_RESEARCH_BANNER_TEXT = `${RESEARCH_BANNER_LEAD} ${METHODOLOGY_RESEARCH_BANNER_BODY}`;
