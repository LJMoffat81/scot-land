"use client";

import PlaceCard from "@/components/PlaceCard";
import {
  PLACE_CARD_HOW_WE_WORK_LABEL,
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
  /** Search found nothing in Scotland. */
  noMatch?: boolean;
  /** True after postcode / address / place-name search (not map click). */
  fromAddressSearch?: boolean;
  /** GRID-BASE-1 row-6 grid square line (or null/empty when none). */
  gridSquareLine?: string | null;
};

type PlaceCardStubProps = {
  place: PlaceStub;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  /** SW-028: sea stub — close + national Scotland map view. */
  onShowScotland?: () => void;
  /** GRID-BASE-1 row-6 override (falls back to place.gridSquareLine). */
  gridSquareLine?: string | null;
};

/** Map HUD place card — UX-10 skeleton; thin wrapper over PlaceCard. */
export default function PlaceCardStub({
  place,
  loading = false,
  error = null,
  onClose,
  onShowScotland,
  gridSquareLine = null,
}: PlaceCardStubProps) {
  const row6 = gridSquareLine ?? place.gridSquareLine ?? null;
  if (place.noMatch) {
    return (
      <PlaceCard
        data={{
          contract: "place_card_v1",
          lat: place.lat,
          lng: place.lng,
          card_state: "no_match",
          place_label: null,
          layers: [],
          links: [],
        }}
        isLoading={loading}
        error={error}
        onClose={onClose}
        floating
        className="place-card-stub"
        noMatch
        fromAddressSearch={Boolean(place.fromAddressSearch)}
        gridSquareLine={row6}
      />
    );
  }

  const data: PlaceCardPayload =
    place.card ??
    ({
      contract: "place_card_v1",
      lat: place.lat,
      lng: place.lng,
      place_label: place.label ?? place.dataZoneName ?? null,
      postcode: place.postcode ?? null,
      council_name: place.laName ?? null,
      dwellings: place.dwellings ?? null,
      data_zone: place.dataZoneCode
        ? {
            status: "ok",
            code: place.dataZoneCode,
            name: place.dataZoneName ?? null,
            vintage: place.dataZoneVintage ?? null,
          }
        : { status: "pending" },
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
        { id: "methodology", label: PLACE_CARD_HOW_WE_WORK_LABEL, url: "/methodology" },
      ],
    } satisfies PlaceCardPayload);

  const merged: PlaceCardPayload = {
    ...data,
    dwellings:
      typeof place.dwellings === "number" ? place.dwellings : data.dwellings,
    place_label: data.place_label ?? place.label ?? place.dataZoneName ?? null,
    council_name: data.council_name ?? place.laName ?? null,
  };

  return (
    <PlaceCard
      data={merged}
      isLoading={loading}
      error={error}
      onClose={onClose}
      onShowScotland={onShowScotland}
      floating
      className="place-card-stub"
      fromAddressSearch={Boolean(place.fromAddressSearch)}
      dwellings={place.dwellings ?? merged.dwellings ?? null}
      gridSquareLine={row6}
    />
  );
}
