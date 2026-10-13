/**
 * Dev/QA preview routes (/ledger-panel, /layers-panel, /place-card,
 * /tax-scenario-panel) stay off the public build unless
 * NEXT_PUBLIC_ENABLE_INTERNAL_UI=1.
 */

export function internalUiEnabled(): boolean {
  return process.env.NEXT_PUBLIC_ENABLE_INTERNAL_UI === "1";
}
