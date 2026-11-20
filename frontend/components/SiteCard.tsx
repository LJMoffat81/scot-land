"use client";

import {
  SITE_CARD_CLOSE_ARIA_LABEL,
  SITE_CARD_CLOSE_LABEL,
  type SiteCardData,
} from "../lib/siteCard";

/**
 * SITE-CLICK-FALLTHROUGH-1 — compact card for a click on a visible HLS / LDP
 * site. Same shell as the place card; no disclaimer footer (PL ruling
 * 2026-11-20) and no new banner.
 */
export function SiteCard({
  data,
  onClose,
}: {
  data: SiteCardData;
  onClose: () => void;
}) {
  const firstId = `site-card-heading-${data.sections[0]?.kind ?? "hls"}`;
  return (
    <aside
      className="hud-card hud-place place-card site-card"
      role="region"
      aria-labelledby={firstId}
      data-testid="site-card"
    >
      <div className="place-card-body site-card-body">
        {data.sections.map((section, index) => (
          <section
            key={section.kind}
            className="site-card-section"
            data-testid={`site-card-${section.kind}`}
          >
            <div className="site-card-head">
              <h2
                className="place-card-title site-card-heading"
                id={`site-card-heading-${section.kind}`}
                data-testid={`site-card-${section.kind}-heading`}
              >
                {section.heading}
              </h2>
              {index === 0 ? (
                <button
                  type="button"
                  className="site-card-close"
                  onClick={onClose}
                  aria-label={SITE_CARD_CLOSE_ARIA_LABEL}
                  data-testid="site-card-close"
                >
                  {SITE_CARD_CLOSE_LABEL}
                </button>
              ) : null}
            </div>
            {section.rows.length ? (
              <dl className="site-card-rows">
                {section.rows.map((row) => (
                  <div
                    key={row.label}
                    className="site-card-row"
                    data-testid={`site-card-${section.kind}-row`}
                  >
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            <p
              className="site-card-note"
              data-testid={`site-card-${section.kind}-note`}
            >
              {section.note}
            </p>
            <p
              className="layer-meta site-card-source"
              data-testid={`site-card-${section.kind}-source`}
            >
              {section.source}
            </p>
          </section>
        ))}
      </div>
    </aside>
  );
}

export default SiteCard;
