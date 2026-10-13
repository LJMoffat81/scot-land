"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import PlaceHectareStack from "@/components/PlaceHectareStack";
import { visitorFacingError } from "@/lib/api";
import {
  fetchPlaceStack,
  PLACE_STACK_BLOCKED_FIXTURE,
  PLACE_STACK_FIXTURE,
  type PlaceHectareStackPayload,
} from "@/lib/placeStack";

function PlaceNav() {
  return (
    <p className="downloads-nav">
      <a href="/">Map</a>
      {" · "}
      <a href="/data">Data</a>
      {" · "}
      <a href="/methodology">About</a>
      {" · "}
      <a href="/place" aria-current="page">
        Place
      </a>
    </p>
  );
}

/**
 * Full place page — per-hectare Natural capital stack (FRONTEND_IA §4).
 * Offline preview: /place or /place?fixture=1 ; blocked: ?fixture=blocked.
 * Live: /place?zone=S01… or /place?lat=&lng=.
 */
function PlacePageInner() {
  const params = useSearchParams();
  const zone = params.get("zone");
  const lat = params.get("lat");
  const lng = params.get("lng");
  const fixture = params.get("fixture");

  const live =
    fixture == null && Boolean(zone || (lat != null && lng != null));

  const [data, setData] = useState<PlaceHectareStackPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!live) {
      setData(
        fixture === "blocked"
          ? PLACE_STACK_BLOCKED_FIXTURE
          : PLACE_STACK_FIXTURE,
      );
      setLoading(false);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    fetchPlaceStack({
      zone,
      lat: lat != null ? Number(lat) : null,
      lng: lng != null ? Number(lng) : null,
    })
      .then((body) => {
        if (!cancelled) {
          setData(body);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setData(null);
          setError(visitorFacingError(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [live, zone, lat, lng, fixture]);

  return (
    <main className="downloads-page place-stack-page" data-testid="place-page">
      <PlaceNav />
      <PlaceHectareStack data={data} isLoading={loading} error={error} />
    </main>
  );
}

export default function PlacePage() {
  return (
    <Suspense
      fallback={
        <main className="downloads-page place-stack-page">Loading…</main>
      }
    >
      <PlacePageInner />
    </Suspense>
  );
}
