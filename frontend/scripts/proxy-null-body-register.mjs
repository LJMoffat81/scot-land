/**
 * Resolve the proxy route's extensionless `lib/api` import under Node's
 * type stripper. The Next bundler resolves that specifier; this test does not.
 */
import { register } from "node:module";

register("./proxy-null-body-hook.mjs", import.meta.url);
