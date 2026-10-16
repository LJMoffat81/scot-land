/**
 * ROADMAP-LEVELS-1 — the same five levels on the roadmap and How it works.
 * Data Zone is the level the map shows now. The two finer levels come later.
 */
export const AREA_LEVELS = [
  "Scotland",
  "council area",
  "Data Zone, live",
  "RoS land parcel",
  "3m grid squares, later",
] as const;

export const AREA_LEVELS_EXPLANATION =
  "These five levels nest. Each larger area is made from the areas inside it, starting from the one below. The map shows Data Zones now. RoS land parcels and 3m grid squares come later. We do not publish a Scotland total or a council total yet.";
