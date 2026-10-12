"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import PlaceCard from "@/components/PlaceCard";
import { PLACE_CARD_FIXTURE } from "@/lib/placeCard";

/**
 * Standalone place-card preview for demos, e2e, and screenshots.
 * Not the w3w map shell — that wires PlaceCard later via /platform/place.
 */
function PlaceCardPreviewInner() {
  const params = useSearchParams();
  const variant = params.get("variant") || "hit";

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
          if (layer.id === "la_holdings" || layer.id === "sasine_private") {
            return layer;
          }
          return layer;
        }),
        land_register_outline: {
          status: "no_outline",
          note: "We found no Land Register boundary at this point.",
        },
        flags: ["no_inspire_parcel"],
      };
    }
    if (variant === "vdl") {
      return {
        ...PLACE_CARD_FIXTURE,
        vacant_or_derelict: true,
        layers: PLACE_CARD_FIXTURE.layers.map((layer) =>
          layer.id === "vdl"
            ? {
                ...layer,
                intersects: true,
                detail: {
                  sites: [
                    {
                      name: "Demo vacant site",
                      site_type: "Vacant Land",
                      size_ha: 0.4,
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
        Standalone place-card preview ({variant}). Slots into the w3w shell via{" "}
        <code>GET /platform/place</code>. No modelled Annual Ground Rent.
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
