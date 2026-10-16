"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import PlaceCard from "@/components/PlaceCard";
import { PLACE_CARD_FIXTURE } from "@/lib/placeCard";

const INTERNAL_PREVIEWS =
  process.env.NEXT_PUBLIC_INTERNAL_PREVIEWS === "1" ||
  process.env.NEXT_PUBLIC_ENABLE_INTERNAL_PREVIEWS === "1";

/**
 * Internal-only place-card preview (Designer brief v3.1).
 * Public place card lives on the map (`/`). Enable with
 * NEXT_PUBLIC_INTERNAL_PREVIEWS=1 for Dev/QA / e2e.
 */
function PlaceCardPreviewInner() {
  const params = useSearchParams();
  const variant = params.get("variant") || "hit";

  if (!INTERNAL_PREVIEWS) {
    return (
      <main className="place-card-preview" data-testid="place-card-internal-only">
        <h1>Internal preview</h1>
        <p>
          The place card lives on the map. This standalone route is not part of
          the public build.
        </p>
        <p>
          <a href="/">Open the map</a>
        </p>
      </main>
    );
  }

  const data = useMemo(() => {
    if (variant === "gap") {
      return {
        ...PLACE_CARD_FIXTURE,
        vacant_or_derelict: false,
        parcel: { found: false, label: null, inspire_id: null, area_sqm: null },
        layers: PLACE_CARD_FIXTURE.layers.map((layer) => {
          if (layer.id === "boundaries") {
            return {
              ...layer,
              intersects: false,
              note: "No Land Register outline at this point.",
              detail: undefined,
            };
          }
          return layer;
        }),
        land_register_outline: {
          status: "no_outline",
          note:
            "We found no Land Register boundary at this point. Its title may still be in " +
            "the older Sasine register, or the land may not be registered at all. We estimate " +
            "it by area and land type, and show no boundaries, titles or owners.",
        },
        land_outline: {
          status: "no_outline",
          label: "Land outline",
          area_sqm: null,
          note:
            "We found no Land Register boundary at this point. Its title may still be in " +
            "the older Sasine register, or the land may not be registered at all. We estimate " +
            "it by area and land type, and show no boundaries, titles or owners.",
        },
        flags: ["no_inspire_parcel"],
      };
    }
    if (variant === "vdl") {
      return {
        ...PLACE_CARD_FIXTURE,
        vacant_or_derelict: true,
        constraints: (PLACE_CARD_FIXTURE.constraints || []).map((row) =>
          row.id === "vdl" ? { ...row, applies: true } : row,
        ),
        layers: PLACE_CARD_FIXTURE.layers.map((layer) =>
          layer.id === "vdl"
            ? {
                ...layer,
                intersects: true,
                detail: {
                  data_zones: [
                    {
                      data_zone: "S01014567",
                      vintage: 2022,
                      site_count: "<3",
                      area_ha: null,
                    },
                  ],
                },
              }
            : layer,
        ),
        flags: ["vacant_or_derelict_survey", "registered_cadastre"],
      };
    }
    return PLACE_CARD_FIXTURE;
  }, [variant]);

  return (
    <main className="place-card-preview" data-testid="place-card-preview">
      <div className="place-card-preview-stage">
        <PlaceCard data={data} floating={false} />
      </div>
      <p className="place-card-preview-note">
        Internal place-card preview ({variant}). Public card is on the map.
        Designer brief v3.1 field order; figures pending sign-off — no £.
      </p>
    </main>
  );
}

export default function PlaceCardPreviewPage() {
  return (
    <Suspense fallback={<main className="place-card-preview">Loading…</main>}>
      <PlaceCardPreviewInner />
    </Suspense>
  );
}
