"use client";

import { useEffect, useRef, useState } from "react";

import ResearchBanner from "@/components/ResearchBanner";
import SiteNav from "@/components/SiteNav";
import { apiJson } from "@/lib/api";

const SWAGGER_CSS = "/swagger-ui/swagger-ui.css";
const SWAGGER_BUNDLE = "/swagger-ui/swagger-ui-bundle.js";
const SWAGGER_PRESET = "/swagger-ui/swagger-ui-standalone-preset.js";
const OPENAPI_URL = "/backend/openapi.json";

type CatalogLayerNote = {
  id: string;
  label?: string;
  developer_note?: string;
};

type SwaggerUIBundleFn = (opts: Record<string, unknown>) => unknown;

declare global {
  interface Window {
    SwaggerUIBundle?: SwaggerUIBundleFn & {
      presets?: { apis?: unknown };
      plugins?: { DownloadUrl?: unknown };
    };
    SwaggerUIStandalonePreset?: unknown;
  }
}

function loadStylesheet(href: string): void {
  if (document.querySelector(`link[data-swagger-href="${href}"]`)) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  link.dataset.swaggerHref = href;
  document.head.appendChild(link);
}

function loadScript(src: string): Promise<void> {
  const existing = document.querySelector(
    `script[data-swagger-src="${src}"]`,
  ) as HTMLScriptElement | null;
  if (existing) {
    if (existing.dataset.loaded === "1") return Promise.resolve();
    return new Promise((resolve, reject) => {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error(`Failed to load ${src}`)),
        { once: true },
      );
    });
  }
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.dataset.swaggerSrc = src;
    script.onload = () => {
      script.dataset.loaded = "1";
      resolve();
    };
    script.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.body.appendChild(script);
  });
}

/**
 * Self-hosted Swagger UI at /developers/api.
 * Assets live under /swagger-ui/ (vendored swagger-ui-dist) so the
 * docs page stays within the default same-origin CSP.
 */
export default function ApiReferencePage() {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [devNotes, setDevNotes] = useState<CatalogLayerNote[]>([]);

  useEffect(() => {
    let cancelled = false;
    void apiJson<{ layers?: CatalogLayerNote[] }>("/api/catalog.json")
      .then((body) => {
        if (cancelled) return;
        const notes = (body.layers ?? []).filter((layer) =>
          Boolean(layer.developer_note?.trim()),
        );
        setDevNotes(notes);
      })
      .catch(() => {
        if (!cancelled) setDevNotes([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function mount() {
      try {
        loadStylesheet(SWAGGER_CSS);
        await loadScript(SWAGGER_BUNDLE);
        await loadScript(SWAGGER_PRESET);
        if (cancelled || !hostRef.current) return;

        const bundle = window.SwaggerUIBundle;
        if (!bundle) {
          throw new Error("SwaggerUIBundle failed to load");
        }

        hostRef.current.innerHTML = "";
        const mountEl = document.createElement("div");
        mountEl.id = "swagger-ui";
        hostRef.current.appendChild(mountEl);

        const presets = [bundle.presets?.apis, window.SwaggerUIStandalonePreset].filter(
          Boolean,
        );

        bundle({
          url: OPENAPI_URL,
          dom_id: "#swagger-ui",
          deepLinking: true,
          presets,
          plugins: bundle.plugins?.DownloadUrl
            ? [bundle.plugins.DownloadUrl]
            : [],
          layout: "StandaloneLayout",
          tryItOutEnabled: true,
        });
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "API reference failed to load.",
          );
        }
      }
    }

    void mount();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="downloads-page" data-testid="api-reference-page">
      <SiteNav current="developers" />
      <h1>API reference</h1>
      <ResearchBanner />
      <p>
        OpenAPI for the place and layer API. Assets are served from this site
        (no CDN). Schema:{" "}
        <a href={OPENAPI_URL}>
          <code>{OPENAPI_URL}</code>
        </a>
        . Overview: <a href="/developers">Downloads &amp; API</a>.
      </p>
      {devNotes.length > 0 ? (
        <section
          className="api-dev-notes"
          data-testid="catalog-developer-notes"
          aria-label="Catalogue technical notes"
        >
          <h2>Catalogue technical notes</h2>
          <p className="downloads-note">
            Developer-only ingest detail from{" "}
            <code>/api/catalog.json</code> (<code>developer_note</code>). Visitor
            pages use the plain-English <code>description</code> field instead.
          </p>
          <ul>
            {devNotes.map((layer) => (
              <li key={layer.id} data-developer-note-id={layer.id}>
                <strong>{layer.label || layer.id}</strong>
                <pre className="download-path">{layer.developer_note}</pre>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {error && <p className="downloads-note">{error}</p>}
      <div
        ref={hostRef}
        className="api-docs-swagger-host"
        data-testid="swagger-host"
      />
    </main>
  );
}
