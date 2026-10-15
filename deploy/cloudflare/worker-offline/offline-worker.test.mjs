/**
 * Unit test: offline Worker with a mocked failing origin.
 * Run: node --test deploy/cloudflare/worker-offline/offline-worker.test.mjs
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  OFFLINE_MESSAGE,
  handleRequest,
  offlineResponse,
} from "./src/index.js";

describe("offline Worker", () => {
  it("serves the offline message when origin fetch throws", async () => {
    const res = await handleRequest(new Request("https://scot-land.scot/"), {
      fetch: async () => {
        throw new TypeError("Origin unreachable");
      },
    });
    assert.equal(res.status, 503);
    assert.equal(await res.text(), OFFLINE_MESSAGE);
    assert.match(res.headers.get("Content-Type") || "", /text\/plain/);
  });

  it("serves the offline message on Cloudflare origin-down statuses", async () => {
    for (const status of [521, 522, 523, 530]) {
      const res = await handleRequest(new Request("https://scot-land.scot/map"), {
        fetch: async () => new Response("error", { status }),
      });
      assert.equal(res.status, 503, `status ${status}`);
      assert.equal(await res.text(), OFFLINE_MESSAGE);
    }
  });

  it("passes through a healthy origin response", async () => {
    const res = await handleRequest(new Request("https://scot-land.scot/"), {
      fetch: async () =>
        new Response("ok", {
          status: 200,
          headers: { "Content-Type": "text/html" },
        }),
    });
    assert.equal(res.status, 200);
    assert.equal(await res.text(), "ok");
  });

  it("offlineResponse matches the frozen public copy", () => {
    const res = offlineResponse();
    assert.equal(
      OFFLINE_MESSAGE,
      "Scot-LAND is offline for a short while. Please try again later.",
    );
    assert.equal(res.status, 503);
  });
});
