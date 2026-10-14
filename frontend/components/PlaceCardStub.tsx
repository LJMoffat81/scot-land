"use client";

import PlaceCard from "@/components/PlaceCard";
import {
  PLACE_CARD_HOW_WE_WORK_LABEL,
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
  /** Search found nothing in Scotland. */
  noMatch?: boolean;
  /** True after postcode / address / place-name search (not map click). */
  fromAddressSearch?: boolean;
};

type PlaceCardStubProps = {
  place: PlaceStub;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
  /** SW-028: sea stub — close + national Scotland map view. */
  onShowScotland?: () => void;
};

/** Map HUD place card — UX-10 skeleton; thin wrapper over PlaceCard. */
export default function PlaceCardStub({
  place,
  loading = false,
  error = null,
  onClose,
  onShowScotland,
}: PlaceCardStubProps) {
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
    />
  );
}
