"use client";

import { useEffect, useId, useRef, useState } from "react";

import {
  SITE_NAV_ITEMS,
  type SiteNavId,
} from "@/lib/siteNav";

export type SiteNavProps = {
  /** Current page — sets aria-current="page". Omit on pages outside the main nav. */
  current?: SiteNavId;
  /**
   * page — full top bar with logo (content pages).
   * map — compact links for the map HUD (logo stays in hud-brand).
   */
  variant?: "page" | "map";
};

const MOBILE_MAX = 600;

/**
 * Site-wide nav: Map · About · How we built this · How it works · Data & sources · Downloads & API.
 * Mobile (≤600px): hamburger menu with backdrop (SW-011).
 */
export default function SiteNav({
  current,
  variant = "page",
}: SiteNavProps) {
  const menuId = useId();
  const navRef = useRef<HTMLElement | null>(null);
  const menuBtnRef = useRef<HTMLButtonElement | null>(null);
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
      if (event.key !== "Escape") return;
      setOpen(false);
      // UX-03: return focus to the hamburger that opened the menu.
      menuBtnRef.current?.focus();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      const root = navRef.current;
      if (!root) return;
      const target = event.target;
      if (target instanceof Node && root.contains(target)) return;
      setOpen(false);
    };
    // Capture so map HUD / page chrome taps close the menu even with
    // pointer-events:none ancestors.
    document.addEventListener("pointerdown", onPointer, true);
    return () => document.removeEventListener("pointerdown", onPointer, true);
  }, [open]);

  useEffect(() => {
    if (!open || !isMobile) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open, isMobile]);

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

  const mobileMenu = isMobile ? (
    <>
      {open ? (
        <button
          type="button"
          className="site-nav-backdrop"
          aria-label="Close menu"
          data-testid="site-nav-backdrop"
          onClick={() => setOpen(false)}
        />
      ) : null}
      <button
        ref={menuBtnRef}
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
  );

  if (variant === "map") {
    return (
      <nav
        ref={navRef}
        className={
          open ? "site-nav site-nav-map site-nav-open" : "site-nav site-nav-map"
        }
        aria-label="Site"
        data-testid="site-nav"
        data-variant="map"
        data-open={open ? "true" : "false"}
      >
        {mobileMenu}
      </nav>
    );
  }

  return (
    <nav
      ref={navRef}
      className={
        open ? "site-nav site-nav-page site-nav-open" : "site-nav site-nav-page"
      }
      aria-label="Site"
      data-testid="site-nav"
      data-variant="page"
      data-open={open ? "true" : "false"}
    >
      <a
        className="site-nav-brand"
        href="/"
        aria-label="Scot-LAND home"
        data-testid="site-nav-brand"
      >
        <img src="/logo-mark-h3.png" alt="" width={40} height={40} />
        <span className="site-nav-brand-text">
          {/* Logo mark already includes LAND; hide this text on mobile (SW-020). */}
          <span className="site-nav-wordmark">Scot-LAND</span>
          <span className="site-nav-tagline">Land value we all create</span>
        </span>
      </a>
      {mobileMenu}
    </nav>
  );
}
