/**
 * LOOKUP-DEADLINES-1 — api timeout, 524, classification, retired copy.
 * Run: npm run test:lookup-deadlines-1
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { mock, test } from "node:test";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const apiHref = pathToFileURL(join(frontendRoot, "lib/api.ts")).href;
const placeCardHref = pathToFileURL(join(frontendRoot, "lib/placeCard.ts")).href;

const api = await import(apiHref);
const placeCard = await import(placeCardHref);

const {
  ApiError,
  DEFAULT_API_TIMEOUT_MS,
  LOOKUP_TIMEOUT_MS,
  apiFetch,
  lookupErrorKind,
  normaliseTimeoutMs,
  placeLookupFetch,
} = api;

const originalFetch = globalThis.fetch;

function restoreFetch() {
  globalThis.fetch = originalFetch;
}

async function flush() {
  for (let i = 0; i < 8; i += 1) {
    await new Promise((resolve) => {
      setImmediate(resolve);
    });
  }
}

function abortError() {
  return new DOMException("The operation was aborted.", "AbortError");
}

function jsonResponse(status) {
  return new Response(JSON.stringify({ detail: "stub" }), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** Fetch that settles only when its signal aborts. Captures the last init. */
function hangingFetch() {
  const captured = [];
  globalThis.fetch = (_url, init) => {
    captured.push(init);
    return new Promise((_resolve, reject) => {
      const signal = init?.signal;
      if (!signal) return;
      if (signal.aborted) {
        reject(abortError());
        return;
      }
      signal.addEventListener("abort", () => {
        reject(abortError());
      });
    });
  };
  return captured;
}

test("locked copy and generic line is defined once", () => {
  assert.equal(
    placeCard.LOOKUP_ERROR_COPY,
    "We couldn't load this area just now.",
  );
  assert.equal(
    placeCard.PLACE_CARD_ERROR_LINE,
    "Something went wrong. Please try again.",
  );
  assert.equal(placeCard.PLACE_CARD_TRY_AGAIN_LABEL, "Try again");
  assert.equal(placeCard.LOOKUP_ERROR_COPY.includes("\u2019"), false);

  const retrySrc = readFileSync(
    join(frontendRoot, "components/RetryState.tsx"),
    "utf8",
  );
  assert.match(
    retrySrc,
    /export const RETRY_STATE_GENERIC_COPY = "This didn't load just now.";/,
  );
  const hits = [];
  for (const root of ["components", "lib", "app"]) {
    walkDir(join(frontendRoot, root), (rel, text) => {
      if (!rel.endsWith(".ts") && !rel.endsWith(".tsx")) return;
      if (text.includes("RETRY_STATE_GENERIC_COPY")) hits.push(rel);
    });
  }
  assert.deepEqual(hits, ["components/RetryState.tsx"]);
});

test("N7 normaliseTimeoutMs falls back", () => {
  const fallback = 4242;
  for (const value of [0, -1, undefined, null, Number.NaN, Infinity, "20"]) {
    assert.equal(normaliseTimeoutMs(value, fallback), fallback);
  }
  assert.equal(normaliseTimeoutMs(1500, fallback), 1500);
});

test("N7 placeLookupFetch timeoutMs 0 uses the lookup default", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const captured = hangingFetch();
  let settled = false;
  const pending = placeLookupFetch("/place?q=EH1", { timeoutMs: 0 }).then(
    () => {
      settled = true;
      return { kind: "ok" };
    },
    (err) => {
      settled = true;
      return { kind: "err", err };
    },
  );
  await flush();
  mock.timers.tick(LOOKUP_TIMEOUT_MS - 1);
  await flush();
  assert.equal(settled, false);
  assert.equal(captured[0]?.signal?.aborted, false);
  mock.timers.tick(1);
  const result = await pending;
  assert.equal(result.kind, "err");
  assert.equal(result.err instanceof ApiError, true);
  assert.equal(result.err.kind, "timeout");
  mock.timers.reset();
  restoreFetch();
});

test("N7 apiFetch timeoutMs 0 uses the non-lookup default", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  hangingFetch();
  let settled = false;
  const pending = apiFetch("/square", { timeoutMs: 0 }).then(
    () => {
      settled = true;
      return { kind: "ok" };
    },
    (err) => {
      settled = true;
      return { kind: "err", err };
    },
  );
  await flush();
  mock.timers.tick(DEFAULT_API_TIMEOUT_MS - 1);
  await flush();
  assert.equal(settled, false);
  mock.timers.tick(1);
  const result = await pending;
  assert.equal(result.kind, "err");
  assert.equal(result.err.kind, "timeout");
  mock.timers.reset();
  restoreFetch();
});

test("N7 omitted timeoutMs on a non-lookup call uses the default", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  hangingFetch();
  let settled = false;
  const pending = apiFetch("/health").then(
    () => {
      settled = true;
      return { kind: "ok" };
    },
    (err) => {
      settled = true;
      return { kind: "err", err };
    },
  );
  await flush();
  mock.timers.tick(DEFAULT_API_TIMEOUT_MS - 1);
  await flush();
  assert.equal(settled, false);
  mock.timers.tick(1);
  const result = await pending;
  assert.equal(result.err.kind, "timeout");
  mock.timers.reset();
  restoreFetch();
});

test("U2 524 is retried once then terminal", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const statuses = [524, 524, 200];
  let calls = 0;
  globalThis.fetch = async () => {
    const status = statuses[calls] ?? 200;
    calls += 1;
    return jsonResponse(status);
  };
  const pending = apiFetch("/platform/place", {
    retryStatuses: [503],
    maxAttempts: 3,
  }).then(
    () => ({ rejected: false }),
    (err) => ({ rejected: true, err }),
  );
  await flush();
  mock.timers.tick(250);
  await flush();
  const result = await pending;
  assert.equal(calls, 2);
  assert.equal(result.rejected, true);
  assert.equal(result.err.kind, "origin_timeout");
  assert.equal(result.err.status, 524);
  mock.timers.reset();
  restoreFetch();
});

test("U2 503 then two 524s use three calls", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const statuses = [503, 524, 524];
  let calls = 0;
  globalThis.fetch = async () => {
    const status = statuses[calls] ?? 200;
    calls += 1;
    return jsonResponse(status);
  };
  const pending = apiFetch("/platform/place", {
    retryStatuses: [503],
    maxAttempts: 3,
  }).then(
    () => ({ rejected: false }),
    (err) => ({ rejected: true, err }),
  );
  await flush();
  mock.timers.tick(250);
  await flush();
  mock.timers.tick(500);
  await flush();
  const result = await pending;
  assert.equal(calls, 3);
  assert.equal(result.rejected, true);
  assert.equal(result.err.kind, "origin_timeout");
  assert.equal(result.err.status, 524);
  mock.timers.reset();
  restoreFetch();
});

test("U2 524 with no retryStatuses is a single call", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return jsonResponse(524);
  };
  const err = await apiFetch("/platform/place").then(
    () => {
      throw new Error("expected rejection");
    },
    (caught) => caught,
  );
  assert.equal(calls, 1);
  assert.equal(err.kind, "origin_timeout");
  assert.equal(err.status, 524);
  restoreFetch();
});

test("N9 non-network errors are the same object", async () => {
  const thrown = new RangeError("boom");
  globalThis.fetch = () => {
    throw thrown;
  };
  const err = await apiFetch("/place").then(
    () => {
      throw new Error("expected rejection");
    },
    (caught) => caught,
  );
  assert.strictEqual(err, thrown);
  assert.equal(err instanceof ApiError, false);
  restoreFetch();
});

test("N9 caller abort, TypeError, timer and lookupErrorKind", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const caller = new AbortController();
  hangingFetch();
  const aborted = apiFetch("/place", { signal: caller.signal }).then(
    () => ({ kind: "ok" }),
    (err) => ({ kind: "err", err }),
  );
  await flush();
  caller.abort();
  const abortedResult = await aborted;
  assert.equal(abortedResult.err.kind, "aborted");

  globalThis.fetch = () => {
    throw new TypeError("Failed to fetch");
  };
  const network = await apiFetch("/place").then(
    () => ({ kind: "ok" }),
    (err) => ({ kind: "err", err }),
  );
  assert.equal(network.err.kind, "network");

  hangingFetch();
  const timed = apiFetch("/place", { timeoutMs: 50, maxAttempts: 1 }).then(
    () => ({ kind: "ok" }),
    (err) => ({ kind: "err", err }),
  );
  await flush();
  mock.timers.tick(50);
  const timedResult = await timed;
  assert.equal(timedResult.err.kind, "timeout");
  assert.equal(lookupErrorKind(new Error("x")), null);
  assert.equal(lookupErrorKind(timedResult.err), "timeout");
  mock.timers.reset();
  restoreFetch();
});

test("N9 source pins on lib/api.ts", () => {
  const src = readFileSync(join(frontendRoot, "lib/api.ts"), "utf8");
  assert.doesNotMatch(src, /catch\s*\{\s*throw new ApiError\(TRY_AGAIN, url\);/);
  assert.doesNotMatch(
    src,
    /catch\s*\(\s*\w*\s*\)\s*\{\s*throw new ApiError\(TRY_AGAIN, url\);/,
  );
  assert.match(src, /function classifyFetchRejection\(/);
  assert.match(src, /instanceof TypeError/);
  const start = src.indexOf("function classifyFetchRejection(");
  assert.ok(start >= 0);
  const body = src.slice(start);
  const end = body.search(/\n}\n/);
  assert.ok(end > 0);
  assert.match(body.slice(0, end), /throw err;/);
});

test("N10 timeout does not abort the caller signal", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const caller = new AbortController();
  hangingFetch();
  const pending = apiFetch("/place", {
    signal: caller.signal,
    timeoutMs: 40,
    maxAttempts: 1,
  }).then(
    () => ({ kind: "ok" }),
    (err) => ({ kind: "err", err }),
  );
  await flush();
  mock.timers.tick(40);
  const result = await pending;
  assert.equal(result.err.kind, "timeout");
  assert.equal(caller.signal.aborted, false);
  mock.timers.reset();
  restoreFetch();
});

test("N11 a finished request does not abort a later tick", async () => {
  mock.timers.enable({ apis: ["setTimeout"] });
  const captured = [];
  globalThis.fetch = async (_url, init) => {
    captured.push(init);
    return jsonResponse(200);
  };
  const response = await placeLookupFetch("/place?q=ok");
  assert.equal(response.ok, true);
  assert.equal(captured.length, 1);
  const signal = captured[0].signal;
  mock.timers.tick(LOOKUP_TIMEOUT_MS * 2);
  await flush();
  assert.equal(signal.aborted, false);
  assert.equal(captured.length, 1);
  mock.timers.reset();
  restoreFetch();
});

test("retired postcode-unavailable copy is gone under frontend", () => {
  const retired = [
    "Postcode search is unavailable right now.",
    "Click the map instead.",
  ].join(" ");
  const hits = [];
  walkFrontend((rel, text) => {
    if (text.includes(retired)) hits.push(rel);
  });
  assert.deepEqual(hits, [], `retired copy still present in: ${hits.join(", ")}`);
});

const SKIP_DIRS = new Set([
  "node_modules",
  ".next",
  "test-results",
  "playwright-report",
  "out",
  "coverage",
]);

const SOURCE_EXT = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".json",
  ".md",
  ".css",
  ".html",
  ".txt",
  ".yml",
  ".yaml",
]);

function walkFrontend(onFile) {
  walkDir(frontendRoot, onFile);
}

function walkDir(start, onFile) {
  const stack = [start];
  while (stack.length > 0) {
    const dir = stack.pop();
    for (const name of readdirSync(dir)) {
      if (SKIP_DIRS.has(name)) continue;
      const abs = join(dir, name);
      const info = statSync(abs);
      if (info.isDirectory()) {
        stack.push(abs);
        continue;
      }
      const dot = name.lastIndexOf(".");
      const ext = dot >= 0 ? name.slice(dot) : "";
      if (!SOURCE_EXT.has(ext)) continue;
      const text = readFileSync(abs, "utf8");
      onFile(relative(frontendRoot, abs), text);
    }
  }
}
