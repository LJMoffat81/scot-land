/**
 * Rewrites E2E_HOOK_GATE to a boolean literal before bundling.
 * A visitor build becomes `false` so the hook block can be dropped.
 * The Playwright build sets NEXT_PUBLIC_E2E_HOOKS=1 and keeps the hooks.
 */
module.exports = function e2eHooksFlagLoader(source) {
  if (!source.includes("E2E_HOOK_GATE")) return source;
  const enabled = process.env.NEXT_PUBLIC_E2E_HOOKS === "1";
  return source.replaceAll("E2E_HOOK_GATE", enabled ? "true" : "false");
};
