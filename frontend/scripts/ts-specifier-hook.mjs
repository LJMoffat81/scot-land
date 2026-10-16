/**
 * Resolve extensionless `./module` imports inside TypeScript files when a
 * node --experimental-strip-types test loads them directly.
 */
export async function resolve(specifier, context, nextResolve) {
  if (
    (specifier.startsWith("./") || specifier.startsWith("../")) &&
    !/\.(?:mjs|cjs|js|json|ts|tsx|node)$/.test(specifier)
  ) {
    return nextResolve(`${specifier}.ts`, context);
  }
  return nextResolve(specifier, context);
}
