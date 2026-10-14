"use client";

import { useEffect, useId, useState } from "react";

import {
  SITE_NAV_ITEMS,
  type SiteNavId,
} from "@/lib/siteNav";

export type SiteNavProps = {
  /** Current page — sets aria-current="page". */
  current: SiteNavId;
  /**
   * page — full top bar with logo (content pages).
   * map — compact links for the map HUD (logo stays in hud-brand).
   */
  variant?: "page" | "map";
};

const MOBILE_MAX = 600;

/**
 * Site-wide nav: Map · About · How it works · Data & sources · Downloads & API.
 * Mobile (≤600px): hamburger menu.
 */
export default function SiteNav({
  current,
  variant = "page",
}: SiteNavProps) {
  const menuId = useId();
  const [open, setOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${MOBILE_MAX}px)`);
    const sync = () => {
      setIsMobile(mq.matches);
      if (!mq.matches) setOpen(false);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const links = SITE_NAV_ITEMS.map((item) => {
    const isCurrent = item.id === current;
    return (
      <a
        key={item.id}
        href={item.href}
        aria-current={isCurrent ? "page" : undefined}
        onClick={() => setOpen(false)}
      >
        {item.label}
      </a>
    );
  });

  if (variant === "map") {
    return (
      <nav
        className={
          open ? "site-nav site-nav-map site-nav-open" : "site-nav site-nav-map"
        }
        aria-label="Site"
        data-testid="site-nav"
        data-variant="map"
      >
        {isMobile ? (
          <>
            <button
              type="button"
              className="site-nav-menu-btn"
              aria-expanded={open}
              aria-controls={menuId}
              data-testid="site-nav-menu-btn"
              onClick={() => setOpen((v) => !v)}
            >
              <span className="site-nav-menu-icon" aria-hidden="true">
                ☰
              </span>
              <span className="sr-only">Menu</span>
            </button>
            <div
              id={menuId}
              className="site-nav-panel"
              hidden={!open}
              data-testid="site-nav-panel"
            >
              {links}
            </div>
          </>
        ) : (
          <div className="site-nav-links" data-testid="site-nav-links">
            {links}
          </div>
        )}
      </nav>
    );
  }

  return (
    <nav
      className={
        open ? "site-nav site-nav-page site-nav-open" : "site-nav site-nav-page"
      }
      aria-label="Site"
      data-testid="site-nav"
      data-variant="page"
    >
      <a
        className="site-nav-brand"
        href="/"
        aria-label="Scot-LAND"
        data-testid="site-nav-brand"
      >
        <img src="/scot-land-mark.png" alt="" width={40} height={40} />
        <span>Scot-LAND</span>
      </a>
      {isMobile ? (
        <>
          <button
            type="button"
            className="site-nav-menu-btn"
            aria-expanded={open}
            aria-controls={menuId}
            data-testid="site-nav-menu-btn"
            onClick={() => setOpen((v) => !v)}
          >
            <span className="site-nav-menu-icon" aria-hidden="true">
              ☰
            </span>
            <span className="sr-only">Menu</span>
          </button>
          <div
            id={menuId}
            className="site-nav-panel"
            hidden={!open}
            data-testid="site-nav-panel"
          >
            {links}
          </div>
        </>
      ) : (
        <div className="site-nav-links" data-testid="site-nav-links">
          {links}
        </div>
      )}
    </nav>
  );
}
