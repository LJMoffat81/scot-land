/**
 * DEFAULT-3D-VIEW (scot-land.md:167-168):
 * Unit + negative tests for default3dView.ts & p=/br= URL state,
 * plus Playwright e2e verification on desktop (1280x800) and mobile (390x844).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  injectEsriBasemapKey,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import {
  DEFAULT_3D_BEARING,
  DEFAULT_3D_PITCH_DESKTOP,
  DEFAULT_3D_PITCH_MOBILE,
  SCOTLAND_SKY_SPEC,
  VIEW_3D_TOGGLE_ARIA_LABEL_2D,
  VIEW_3D_TOGGLE_ARIA_LABEL_3D,
  defaultOpeningPitch,
  is3dPitchActive,
  nextTogglePitch,
  validateBearingParam,
  validatePitchParam,
} from "../../lib/default3dView";
import {
  parseBearingParam,
  parsePitchParam,
  readMapUrlState,
  writeMapUrlSearch,
} from "../../lib/mapUrlState";

registerOpenFreeMapFontStub();

test("N-3D-1 MapLibre v5 dependency & SCOTLAND_SKY_SPEC (no globe)", () => {
  const pkg = JSON.parse(
    readFileSync(join(__dirname, "..", "..", "package.json"), "utf-8"),
  ) as { dependencies?: Record<string, string> };
  expect(pkg.dependencies?.["maplibre-gl"]).toMatch(/^\^?5\./);
  expect(SCOTLAND_SKY_SPEC).toEqual({
    "sky-color": "#dbeafe",
    "horizon-color": "#f8fafc",
    "fog-color": "#f1f5f9",
    "sky-horizon-blend": 0.5,
    "horizon-fog-blend": 0.5,
    "fog-ground-blend": 0.25,
    "atmosphere-blend": 0.7,
  });
});

test("N-3D-2 defaultOpeningPitch positive & negative checks", () => {
  expect(defaultOpeningPitch(1280, false)).toBe(DEFAULT_3D_PITCH_DESKTOP);
  expect(defaultOpeningPitch(901, false)).toBe(DEFAULT_3D_PITCH_DESKTOP);
  expect(defaultOpeningPitch(900, false)).toBe(DEFAULT_3D_PITCH_MOBILE);
  expect(defaultOpeningPitch(390, false)).toBe(DEFAULT_3D_PITCH_MOBILE);
  expect(defaultOpeningPitch(1280, true)).toBe(0);
  expect(defaultOpeningPitch(390, true)).toBe(0);

  for (const badW of [
    undefined,
    null,
    "",
    0,
    -10,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => defaultOpeningPitch(badW, false)).toThrow(
      /^DEFAULT-3D: viewportWidth must be a positive finite number$/,
    );
  }
  for (const badRm of [null, "", 0, 1, "false", [], {}]) {
    expect(() => defaultOpeningPitch(1280, badRm)).toThrow(
      /^DEFAULT-3D: reducedMotion must be a boolean$/,
    );
  }
});

test("N-3D-3 validatePitchParam & validateBearingParam positive & negative checks", () => {
  expect(validatePitchParam(0)).toBe(0);
  expect(validatePitchParam(55)).toBe(55);
  expect(validatePitchParam("60")).toBe(60);
  expect(validatePitchParam("42.56")).toBe(42.6);
  expect(parsePitchParam(null)).toBeNull();
  expect(parsePitchParam("bad")).toBeNull();

  for (const badP of [
    undefined,
    null,
    "",
    "   ",
    "abc",
    -0.1,
    -10,
    60.1,
    90,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => validatePitchParam(badP)).toThrow(
      /^DEFAULT-3D: pitch must be a finite number in \[0, 60\]$/,
    );
  }

  expect(validateBearingParam(0)).toBe(0);
  expect(validateBearingParam(-0)).toBe(0);
  expect(validateBearingParam("-15")).toBe(-15);
  expect(validateBearingParam(180)).toBe(180);
  expect(validateBearingParam(-180)).toBe(-180);
  expect(parseBearingParam(null)).toBeNull();
  expect(parseBearingParam("bad")).toBeNull();

  for (const badBr of [
    undefined,
    null,
    "",
    "   ",
    "abc",
    -180.1,
    180.1,
    360,
    Number.NaN,
    Number.POSITIVE_INFINITY,
    true,
    false,
    [],
    {},
  ]) {
    expect(() => validateBearingParam(badBr)).toThrow(
      /^DEFAULT-3D: bearing must be a finite number in \[-180, 180\]$/,
    );
  }
});

test("N-3D-4 is3dPitchActive, nextTogglePitch, and URL p=/br= round-trip", () => {
  expect(is3dPitchActive(0)).toBe(false);
  expect(is3dPitchActive(55)).toBe(true);
  expect(nextTogglePitch(60, 1280)).toEqual({ pitch: 0, bearing: 0 });
  expect(nextTogglePitch(0, 1280)).toEqual({
    pitch: 60,
    bearing: DEFAULT_3D_BEARING,
  });
  expect(nextTogglePitch(0, 390)).toEqual({
    pitch: 55,
    bearing: DEFAULT_3D_BEARING,
  });

  const s1 = readMapUrlState("?p=55&br=-15&z=7&c=-3.20000,56.00000");
  expect(s1.p).toBe(55);
  expect(s1.pitch).toBe(55);
  expect(s1.br).toBe(-15);
  expect(s1.bearing).toBe(-15);

  const s2 = readMapUrlState("?pitch=0&bearing=0");
  expect(s2.p).toBe(0);
  expect(s2.br).toBe(0);

  const written = writeMapUrlSearch({
    href: "http://local/",
    p: 55,
    br: -15,
    z: 7,
    center: { lng: -3.2, lat: 56 },
  });
  expect(written).toContain("p=55");
  expect(written).toContain("br=-15");
  const round = readMapUrlState(written);
  expect(round.p).toBe(55);
  expect(round.br).toBe(-15);
});

for (const vp of [
  { width: 1280, height: 800, expectedPitch: 60 },
  { width: 390, height: 844, expectedPitch: 55 },
] as const) {
  test.describe(`E-3D-1 DEFAULT-3D-VIEW @ ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test(`opens tilted at pitch ${vp.expectedPitch}° looking north with sky (no globe), and 2D/3D circular toggle >=44x44 switches between 3D and 2D`, async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await injectEsriBasemapKey(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/");
      await waitForMap(page);
      await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });

      const cam = await page.evaluate(() => {
        const m = (
          window as unknown as {
            __map?: {
              getPitch(): number;
              getBearing(): number;
              getSky?: () => unknown;
              getProjection?: () => { type?: string } | undefined;
            };
          }
        ).__map;
        return {
          pitch: m?.getPitch() ?? -1,
          bearing: m?.getBearing() ?? -999,
          sky: m?.getSky?.() ?? null,
          projection: m?.getProjection?.()?.type ?? "mercator",
        };
      });
      expect(cam.pitch).toBeCloseTo(vp.expectedPitch, 0);
      expect(cam.bearing).toBeCloseTo(0, 0);
      expect(cam.projection).not.toBe("globe");
      expect(cam.sky).toBeTruthy();

      const toggle = page.getByTestId("view-3d-toggle");
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
      await expect(toggle).toHaveAttribute(
        "aria-label",
        VIEW_3D_TOGGLE_ARIA_LABEL_2D,
      );
      await expect(toggle).toHaveText("2D");

      const box = await toggle.boundingBox();
      expect(box).toBeTruthy();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);

      // Verify stacked directly above basemap-switcher without overlap
      const bmBox = await page.getByTestId("basemap-switcher").boundingBox();
      expect(bmBox).toBeTruthy();
      expect(Math.abs(box!.x - bmBox!.x)).toBeLessThanOrEqual(1);
      expect(bmBox!.y - (box!.y + box!.height)).toBeCloseTo(8, 0);

      // Click toggle -> switches to flat 2D (pitch 0, bearing 0)
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-pressed", "false");
      await expect(toggle).toHaveAttribute(
        "aria-label",
        VIEW_3D_TOGGLE_ARIA_LABEL_3D,
      );
      await expect(toggle).toHaveText("3D");
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const m = (
                window as unknown as { __map?: { getPitch(): number } }
              ).__map;
              return m?.getPitch() ?? -1;
            }),
          { timeout: 10_000 },
        )
        .toBeCloseTo(0, 0);
      await expect(page).toHaveURL(/[?&]p=0(&|$)/, { timeout: 10_000 });

      // Click toggle again -> returns to 3D tilted view
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
      await expect(toggle).toHaveText("2D");
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const m = (
                window as unknown as { __map?: { getPitch(): number } }
              ).__map;
              return m?.getPitch() ?? -1;
            }),
          { timeout: 10_000 },
        )
        .toBeCloseTo(vp.expectedPitch, 0);
      // E3D-FIX-1: URL sync runs on moveend, after getPitch() reaches the
      // target; wait for it. Exact match: p=55 (390) / p=60 (1280) only.
      await expect(page).toHaveURL(
        new RegExp(`[?&]p=${vp.expectedPitch}(&|$)`),
        { timeout: 10_000 },
      );
      // Settled camera and URL must agree after the 400 ms ease ends.
      await page.waitForTimeout(600);
      expect(new URL(page.url()).searchParams.get("p")).toBe(
        String(vp.expectedPitch),
      );

      assertConsoleClean(gate);
    });

    test("reduced motion and ?p=0 open flat at pitch 0°", async ({ page }) => {
      test.setTimeout(90_000);
      await page.emulateMedia({ reducedMotion: "reduce" });
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/");
      await waitForMap(page);
      await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });

      const pitch = await page.evaluate(() => {
        const m = (window as unknown as { __map?: { getPitch(): number } }).__map;
        return m?.getPitch() ?? -1;
      });
      expect(pitch).toBeCloseTo(0, 0);
      await expect(page.getByTestId("view-3d-toggle")).toHaveAttribute(
        "aria-pressed",
        "false",
      );
      await expect(page.getByTestId("view-3d-toggle")).toHaveText("3D");

      assertConsoleClean(gate);
    });
  });
}
