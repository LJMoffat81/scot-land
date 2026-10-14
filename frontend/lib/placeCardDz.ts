/**
 * Data Zone vintage helpers for the place card.
 * Kept free of API imports so Node unit tests can import the real functions.
 */

export type PlaceDataZoneVintage = {
  status: "ok" | "miss" | "unavailable" | string;
  code?: string | null;
  name?: string | null;
  vintage?: number | null;
  zones?: Array<{
    code: string;
    vintage: number;
    name?: string | null;
    on_boundary?: boolean;
  }>;
  note?: string | null;
  reasons?: string[];
};

/**
 * Prefer a real DZ2022 entry from `zones[]` when present.
 * Never invent vintage 2022 — keep API vintage (2011 / null) otherwise.
 */
export function preferDz2022(
  zone: PlaceDataZoneVintage | null | undefined,
): PlaceDataZoneVintage | null {
  if (!zone) return null;
  const zones = zone.zones ?? [];
  const dz2022 = zones.find((z) => z.vintage === 2022);
  if (dz2022) {
    return {
      ...zone,
      status: "ok",
      code: dz2022.code,
      name: dz2022.name ?? zone.name,
      vintage: 2022,
    };
  }
  return zone;
}

/** Place-card Data Zone field heading — never label an S01 2011 code as 2022. */
export function dataZoneFieldLabel(
  vintage: number | null | undefined,
): string {
  if (vintage === 2022) return "Data zone (2022)";
  if (vintage === 2011) return "Data zone (2011)";
  return "Data zone";
}
