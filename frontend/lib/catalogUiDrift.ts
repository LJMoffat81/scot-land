/**
 * Catalog ↔ UI drift check: every live catalog layer must have a UI toggle.
 */

export type CatalogUiDriftResult = {
  ok: boolean;
  liveIds: string[];
  toggleIds: string[];
  missingToggles: string[];
  extraToggles: string[];
  message: string;
};

export function checkCatalogUiDrift(
  liveIds: Iterable<string>,
  toggleIds: Iterable<string>,
): CatalogUiDriftResult {
  const live = [...new Set(liveIds)].sort();
  const toggles = [...new Set(toggleIds)].sort();
  const toggleSet = new Set(toggles);
  const liveSet = new Set(live);
  const missingToggles = live.filter((id) => !toggleSet.has(id));
  const extraToggles = toggles.filter((id) => !liveSet.has(id));
  const ok = missingToggles.length === 0;
  let message: string;
  if (ok && extraToggles.length === 0) {
    message = `OK: ${live.length} live catalog layer(s) each have a UI toggle.`;
  } else if (ok) {
    message =
      `OK: live layers covered. Extra UI toggles (not live in catalog): ` +
      extraToggles.join(", ");
  } else {
    message =
      `DRIFT: live catalog layer(s) have no UI toggle: ` +
      missingToggles.join(", ");
  }
  return { ok, liveIds: live, toggleIds: toggles, missingToggles, extraToggles, message };
}
