"use client";

import PlaceCard from "@/components/PlaceCard";
import {
  PLACE_CARD_OUT_OF_SCOTLAND_LINE,
  defaultAgrRows,
  scotLandSquareReference,
  type PlaceCardPayload,
} from "@/lib/placeCard";

export type PlaceStub = {
  lat: number;
  lng: number;
  label?: string | null;
  postcode?: string | null;
  dataZoneCode?: string | null;
  dataZoneName?: string | null;
  /** Open rollups only — never AGR £ / Surface Rent. */
  dataZoneVintage?: number | null;
  laName?: string | null;
  population?: number | null;
  popYear?: number | null;
  dwellings?: number | null;
  dwYear?: number | null;
  /** When set, full place_card_v1 from GET /platform/place. */
  card?: PlaceCardPayload | null;
};

type PlaceCardStubProps = {
  place: PlaceStub;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
};

/** Map HUD place card — Designer v3.1 fields; thin wrapper over PlaceCard. */
export default function PlaceCardStub({
  place,
  loading = false,
  error = null,
  onClose,
}: PlaceCardStubProps) {
  const data: PlaceCardPayload =
    place.card ??
    ({
      contract: "place_card_v1",
      lat: place.lat,
      lng: place.lng,
      place_label: place.label ?? place.dataZoneName ?? null,
      postcode: place.postcode ?? null,
      council_name: place.laName ?? null,
      data_zone: place.dataZoneCode
        ? {
            status: "ok",
            code: place.dataZoneCode,
            name: place.dataZoneName ?? null,
            vintage: place.dataZoneVintage ?? null,
          }
        : { status: "miss", note: PLACE_CARD_OUT_OF_SCOTLAND_LINE },
      intermediate_zone: { status: "no_data", name: null, note: null },
      square_reference: scotLandSquareReference(place.lat, place.lng),
      agr_rows: defaultAgrRows(),
      constraints: [],
      holder: {
        status: "private_not_shown",
        label: "private, not shown",
      },
      layers: [],
      links: [
        { id: "about", label: "About", url: "/about" },
        { id: "methodology", label: "How it works", url: "/methodology" },
      ],
    } satisfies PlaceCardPayload);

  return (
    <PlaceCard
      data={data}
      isLoading={loading}
      error={error}
      onClose={onClose}
      floating
      className="place-card-stub"
    />
  );
}
