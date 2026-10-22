/**
 * LAYERS-FIX-1: upstream 204/205/304 pass through. On 1bdfdf6 a 204 body
 * throws and the proxy answers 503.
 * Run: npm run test:proxy-null-body
 */
import assert from "node:assert/strict";
import { gunzipSync } from "node:zlib";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const { GET, gzipIfTile } = await import(
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

globalThis.fetch = async (_url, init) => {
  assert.equal(init?.headers?.["If-None-Match"], '"oil-etag"');
  return new Response(JSON.stringify({ type: "FeatureCollection", features: [] }), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=86400",
      ETag: '"oil-etag"',
    },
  });
};
try {
  const oil = await GET(
    new Request("http://localhost/backend/layers/context/oil-fields", {
      headers: { "If-None-Match": '"oil-etag"' },
    }),
    { params: Promise.resolve({ path: ["layers", "context", "oil-fields"] }) },
  );
  assert.equal(oil.headers.get("cache-control"), "public, max-age=86400");
  assert.equal(oil.headers.get("etag"), '"oil-etag"');
} finally {
  globalThis.fetch = realFetch;
}

globalThis.fetch = async () =>
  new Response("{}", {
    status: 200,
    headers: { "Cache-Control": "public, max-age=60", "Content-Type": "application/json" },
  });
try {
  const short = await GET(
    new Request("http://localhost/backend/health"),
    { params: Promise.resolve({ path: ["health"] }) },
  );
  assert.equal(short.headers.get("cache-control"), "public, max-age=300");
} finally {
  globalThis.fetch = realFetch;
}

// TF-7: gzipIfTile re-compresses MVT only.
{
  const plain = new TextEncoder().encode("mvt-bytes-here").buffer;
  const mvt = gzipIfTile("application/vnd.mapbox-vector-tile", plain);
  assert.equal(mvt.encoding, "gzip");
  assert.ok(mvt.body);
  assert.equal(
    Buffer.compare(gunzipSync(Buffer.from(mvt.body)), Buffer.from(plain)),
    0,
  );

  const json = gzipIfTile("application/json", plain);
  assert.equal(json.encoding, null);
  assert.equal(json.body, plain);

  const empty = gzipIfTile("application/vnd.mapbox-vector-tile", null);
  assert.equal(empty.body, null);
  assert.equal(empty.encoding, null);
}

// TF-7 via proxy: upstream MVT (already gunzipped by fetch) is re-gzipped.
{
  const plain = Buffer.from("synthetic-mvt-payload");
  globalThis.fetch = async () =>
    new Response(plain, {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.mapbox-vector-tile",
        "Cache-Control": "public, max-age=31536000, immutable",
        ETag: '"abc-5-1-2"',
      },
    });
  try {
    const res = await GET(
      new Request("http://localhost/backend/v1/tiles/dz2022/2026-10-22.abcd1234/5/15/9.mvt"),
      {
        params: Promise.resolve({
          path: ["v1", "tiles", "dz2022", "2026-10-22.abcd1234", "5", "15", "9.mvt"],
        }),
      },
    );
    assert.equal(res.status, 200);
    assert.equal(res.headers.get("content-encoding"), "gzip");
    assert.equal(res.headers.get("vary"), "Accept-Encoding");
    const out = Buffer.from(await res.arrayBuffer());
    assert.equal(Buffer.compare(gunzipSync(out), plain), 0);
  } finally {
    globalThis.fetch = realFetch;
  }
}

console.log("test-proxy-null-body: ok");
