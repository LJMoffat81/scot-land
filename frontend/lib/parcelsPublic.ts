/**
 * PARCELS_PUBLIC gate (default off).
 * Inlined for the client via next.config.ts `env.PARCELS_PUBLIC`.
 * Only the string "true" enables parcel routes and the Land parcels toggle.
 */

export function parcelsPublic(): boolean {
  return process.env.PARCELS_PUBLIC === "true";
}
