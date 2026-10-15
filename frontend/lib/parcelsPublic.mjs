/**
 * PARCELS_PUBLIC gate (default off).
 * Shared .mjs so Node strip-types scripts (place-card-hotfix) can import
 * mapLayerGroups without ERR_MODULE_NOT_FOUND.
 * Only the string "true" enables parcel routes and the Land parcels toggle.
 */

export function parcelsPublic() {
  return process.env.PARCELS_PUBLIC === "true";
}
