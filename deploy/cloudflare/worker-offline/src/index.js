/**
 * Free Cloudflare Worker in front of the home-tunnel origin.
 * When the tunnel or origin is unreachable (or Cloudflare returns an origin-down
 * status), serve a plain offline message — never secrets, never HTML chrome.
 */

export const OFFLINE_MESSAGE =
  "Scot-LAND is offline for a short while. Please try again later.";

/** Cloudflare statuses that mean the origin / tunnel is not serving. */
export const ORIGIN_DOWN_STATUSES = new Set([521, 522, 523, 525, 526, 530]);

export function offlineResponse() {
  return new Response(OFFLINE_MESSAGE, {
    status: 503,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

/**
 * @param {Request} request
 * @param {{ fetch?: typeof fetch }} [deps]  injectable for unit tests
 */
export async function handleRequest(request, deps = {}) {
  const doFetch = deps.fetch ?? globalThis.fetch;
  try {
    const upstream = await doFetch(request);
    if (ORIGIN_DOWN_STATUSES.has(upstream.status)) {
      return offlineResponse();
    }
    return upstream;
  } catch {
    return offlineResponse();
  }
}

export default {
  async fetch(request, _env, _ctx) {
    return handleRequest(request);
  },
};
