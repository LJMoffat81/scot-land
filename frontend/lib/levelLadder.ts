/**
 * ARCH-5c — zoom level ladder, place breadcrumbs, and derived_from slot.
 */

export type LadderLevelId =
  | "scotland"
  | "council"
  | "dz2022"
  | "parcel"
  | "square3m";

export type LadderCrumb = {
  level: "scotland" | "council" | "dz2022";
  label: string;
};

export const SCOTLAND_CRUMB_LABEL = "Scotland";

export function levelFromZoom(...args: unknown[]): LadderLevelId {
  const zoom = args.length === 0 ? undefined : args[0];
  if (typeof zoom !== "number" || !Number.isFinite(zoom)) {
    throw new Error("LEVEL-LADDER: zoom must be a finite number");
  }
  if (zoom < 0 || zoom > 22) {
    throw new Error("LEVEL-LADDER: zoom must be between 0 and 22");
  }
  if (zoom < 6) return "scotland";
  if (zoom < 9) return "council";
  if (zoom < 14) return "dz2022";
  if (zoom < 18) return "parcel";
  return "square3m";
}

export function buildPlaceBreadcrumbs(...args: unknown[]): LadderCrumb[] {
  const opts = args.length === 0 ? undefined : args[0];
  if (typeof opts !== "object" || opts === null || Array.isArray(opts)) {
    throw new Error("LEVEL-LADDER: options must be an object");
  }
  const o = opts as { councilName?: unknown; placeName?: unknown };
  if (
    o.councilName !== undefined &&
    o.councilName !== null &&
    typeof o.councilName !== "string"
  ) {
    throw new Error(
      "LEVEL-LADDER: councilName must be a string or null/undefined",
    );
  }
  if (
    o.placeName !== undefined &&
    o.placeName !== null &&
    typeof o.placeName !== "string"
  ) {
    throw new Error(
      "LEVEL-LADDER: placeName must be a string or null/undefined",
    );
  }
  const crumbs: LadderCrumb[] = [
    { level: "scotland", label: SCOTLAND_CRUMB_LABEL },
  ];
  const council =
    typeof o.councilName === "string" ? o.councilName.trim() : "";
  const place = typeof o.placeName === "string" ? o.placeName.trim() : "";
  if (council) {
    crumbs.push({ level: "council", label: council });
  }
  if (place && place !== council) {
    crumbs.push({ level: "dz2022", label: place });
  }
  return crumbs;
}

export function formatDerivedFromSlot(...args: unknown[]): string {
  const raw = args.length === 0 ? undefined : args[0];
  if (raw === undefined || raw === null) {
    return "";
  }
  if (!Array.isArray(raw)) {
    throw new Error("LEVEL-LADDER: derivedFrom must be an array of strings");
  }
  for (const item of raw) {
    if (typeof item !== "string" || !/^[a-z0-9-]+$/.test(item)) {
      throw new Error("LEVEL-LADDER: derivedFrom items must be non-empty slugs");
    }
  }
  return raw.join(",");
}
