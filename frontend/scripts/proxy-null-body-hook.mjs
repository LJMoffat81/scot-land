export async function resolve(specifier, context, nextResolve) {
  if (specifier === "../../../lib/api" || specifier.endsWith("/lib/api")) {
    return {
      url: new URL(`${specifier}.ts`, context.parentURL).href,
      shortCircuit: true,
    };
  }
  return nextResolve(specifier, context);
}
