/**
 * Register the extensionless `.ts` resolve hook for Node strip-types tests.
 */
import { register } from "node:module";

register("./ts-specifier-hook.mjs", import.meta.url);
