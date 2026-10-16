/**
 * LAYERS-FIX-1: upstream 204/205/304 pass through. On 1bdfdf6 a 204 body
 * throws and the proxy answers 503.
 * Run: npm run test:proxy-null-body
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const { GET } = await import(
  pathToFileURL(join(frontendRoot, "app/backend/[...path]/route.ts")).href
);

const realFetch = globalThis.fetch;

async function proxyStatus(upstreamStatus) {
  globalThis.fetch = async () => new Response(null, { status: upstreamStatus });
  try {
    const response = await GET(
      new Request("http://localhost/backend/tiles/sepa_nfra_grid/12/1/1"),
      { params: Promise.resolve({ path: ["tiles", "sepa_nfra_grid", "12", "1", "1"] }) },
    );
    return response.status;
  } finally {
    globalThis.fetch = realFetch;
  }
}

for (const status of [204, 205, 304]) {
  assert.equal(await proxyStatus(status), status, `upstream ${status}`);
}

globalThis.fetch = async () => {
  throw new Error("upstream down");
};
try {
  const busy = await GET(
    new Request("http://localhost/backend/health"),
    { params: Promise.resolve({ path: ["health"] }) },
  );
  assert.equal(busy.status, 503);
} finally {
  globalThis.fetch = realFetch;
}

console.log("test-proxy-null-body: ok");
