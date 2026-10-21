/**
 * ESRI-KEY-PROD-1 U1 — pure resolveEsriKey / isEsriBasemapKeyConfigured.
 * Dummy keys assembled at runtime so they never match K1.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  isEsriBasemapKeyConfigured,
  resolveEsriKey,
} from "../lib/esriBasemapKey.mjs";

const TEST_KEY = "TEST" + "KEY" + "x".repeat(8);
const HOOK_KEY = "HOOK" + "KEY" + "x".repeat(8);

describe("U1 resolveEsriKey", () => {
  it("(a) envKey present, hooks off → envKey and configured", () => {
    const key = resolveEsriKey({
      envKey: TEST_KEY,
      hooksOn: false,
      injected: undefined,
    });
    assert.equal(key, TEST_KEY);
    assert.equal(isEsriBasemapKeyConfigured(key), true);
  });

  it("(b) empty / whitespace / undefined envKey", () => {
    assert.equal(
      resolveEsriKey({ envKey: "", hooksOn: false, injected: undefined }),
      "",
    );
    assert.equal(isEsriBasemapKeyConfigured(""), false);

    const ws = resolveEsriKey({
      envKey: "   \t",
      hooksOn: false,
      injected: undefined,
    });
    assert.equal(ws, "   \t");
    assert.equal(isEsriBasemapKeyConfigured(ws), false);

    assert.equal(
      resolveEsriKey({
        envKey: undefined,
        hooksOn: false,
        injected: undefined,
      }),
      "",
    );
  });

  it("(c) hooks on: injected string / null / undefined", () => {
    assert.equal(
      resolveEsriKey({
        envKey: TEST_KEY,
        hooksOn: true,
        injected: HOOK_KEY,
      }),
      HOOK_KEY,
    );
    assert.equal(
      resolveEsriKey({
        envKey: TEST_KEY,
        hooksOn: true,
        injected: null,
      }),
      "",
    );
    assert.equal(
      resolveEsriKey({
        envKey: TEST_KEY,
        hooksOn: true,
        injected: undefined,
      }),
      TEST_KEY,
    );
  });

  it("(d) hooks off ignores injected", () => {
    assert.equal(
      resolveEsriKey({
        envKey: "",
        hooksOn: false,
        injected: HOOK_KEY,
      }),
      "",
    );
  });
});
