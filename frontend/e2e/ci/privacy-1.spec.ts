import { expect, test } from "./_fixtures";
import { stubMapCardsBackend } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

/**
 * PRIVACY-1 — contact form states, and a crawl of the sitemap.
 * HTML and first-party JS must not carry GitHub, a name, or an email,
 * except the single allowed phrase on /how-we-built-this.
 */

const EMAIL_RE = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
const ALLOWED = "led by Laurie Moffat";
const FORM_ID = "pwpublic";

function nameHits(text: string, allowPhrase: boolean): string[] {
  const source = allowPhrase ? text.split(ALLOWED).join("") : text;
  return source.match(/Laurie|Moffat/g) ?? [];
}

function isSiteScript(src: string): boolean {
  if (/swagger-ui/i.test(src)) return false;
  if (/node_modules/i.test(src)) return false;
  if (/polyfill/i.test(src)) return false;
  return src.length > 0;
}

async function firstPartyJs(page: Page): Promise<string> {
  const srcs = await page.locator("script[src]").evaluateAll((els) =>
    els.map((el) => el.getAttribute("src") ?? "").filter((src) => src.length > 0),
  );
  const chunks: string[] = [];
  for (const src of srcs) {
    if (!isSiteScript(src)) continue;
    const url = new URL(src, page.url());
    if (url.origin !== new URL(page.url()).origin) continue;
    const response = await page.request.get(url.pathname + url.search);
    if (!response.ok()) continue;
    const text = await response.text();
    // Vendored core-js polyfill, not this site's script.
    if (/zloirock|core-js/i.test(text)) continue;
    chunks.push(text);
  }
  return chunks.join("\n");
}

test.beforeEach(async ({ page }) => {
  await stubMapCardsBackend(page);
});

test.describe("PRIVACY-1 contact form", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("unset id shows coming soon and no address", async ({ page }) => {
    await page.goto("/about#contact");
    await expect(page.getByTestId("contact-form-soon")).toHaveText(
      "Contact form not open yet. Please check back.",
    );
    await expect(page.getByTestId("contact-form")).toHaveCount(0);
    const html = await page.locator("#contact").innerHTML();
    expect(html).not.toMatch(EMAIL_RE);
    expect(html).not.toMatch(/mailto:/i);
  });

  test("flag off stays coming soon even if an id is injected", async ({ page }) => {
    const posts: string[] = [];
    await page.addInitScript((id) => {
      (window as Window & { __SC_CONTACT_FORM_ID?: string }).__SC_CONTACT_FORM_ID =
        id;
    }, FORM_ID);
    await page.route("**/formspree.io/f/**", async (route) => {
      posts.push(route.request().postData() ?? "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });
    await page.goto("/about#contact");
    await expect(page.getByTestId("contact-form-soon")).toHaveText(
      "Contact form not open yet. Please check back.",
    );
    await expect(page.getByTestId("contact-form")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Send" })).toHaveCount(0);
    expect(posts).toEqual([]);
    const html = await page.locator("#contact").innerHTML();
    expect(html).not.toMatch(EMAIL_RE);
    expect(html).not.toMatch(/mailto:/i);
  });
});

test.describe("PRIVACY-1 crawl", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("sitemap pages have no github, name, or email", async ({ page }) => {
    test.setTimeout(180_000);
    const sitemap = await page.request.get("/sitemap.xml");
    expect(sitemap.ok()).toBe(true);
    const xml = await sitemap.text();
    const locs = [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => {
      const url = new URL(match[1]!);
      return url.pathname;
    });
    expect(locs.length).toBeGreaterThan(5);
    const paths = [...new Set([...locs, "/about"])];

    for (const path of paths) {
      await page.goto(path === "/about" ? "/about#contact" : path);
      const html = await page.content();
      const js = await firstPartyJs(page);
      const allow = path === "/how-we-built-this";
      for (const [kind, text] of [
        ["html", html],
        ["js", js],
      ] as const) {
        expect(text, `${path} ${kind} github`).not.toMatch(/github/i);
        expect(nameHits(text, allow), `${path} ${kind} name`).toEqual([]);
        expect(text, `${path} ${kind} email`).not.toMatch(EMAIL_RE);
      }
      if (allow) {
        const visible = await page.getByTestId("how-we-built-copy").innerText();
        expect(visible.match(/led by Laurie Moffat/g)).toEqual([
          "led by Laurie Moffat",
        ]);
      }
      await expect(page.locator('a[href="/about#contact"]')).toHaveCount(0);
    }
  });
});
