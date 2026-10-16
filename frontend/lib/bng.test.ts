/**
 * GRID-BASE-1 — G7 / G14 unit checks (source of truth for fixtures).
 * Executed via `npm run test:bng` → scripts/test-bng.mjs (Node ESM resolver).
 *
 * Fixtures (helmert-v1):
 * - lng −3.1700, lat 55.9750 → E 327080.75, N 676396.73 → key g3:327078:676395, ref "NT 27078 76395"
 * - point on 3 m line floors to that line
 * - round-trip key → corners → centre → same key
 * - "NT 25890 73452" ↔ g3:325890:673452
 * - BNG_TRANSFORM === "helmert-v1"; sole proj4.defs in bng.ts
 */
export {};
