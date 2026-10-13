"use client";

import {
  PLACE_CARD_DATA_ZONE_GRAIN,
  PLACE_CARD_RENT_RANGE_TAGS,
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
};

type PlaceCardStubProps = {
  place: PlaceStub;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
};

function formatCount(value: number): string {
  return value.toLocaleString("en-GB");
}

/**
 * Lightweight place card for the public map shell.
 * Charter: Annual Ground Rent purpose; market/proxy/shadow ranges only;
 * Data Zone grain; no £ figures.
 */
export default function PlaceCardStub({
  place,
  loading = false,
  error = null,
  onClose,
}: PlaceCardStubProps) {
  const title =
    place.label?.trim() ||
    place.postcode?.trim() ||
    place.dataZoneName?.trim() ||
    "This place";

  return (
    <aside className="hud-card hud-place place-card-stub" aria-label="Place">
      <button
        type="button"
        className="hud-close"
        title="Close place (Esc)"
        onClick={onClose}
      >
        ×
      </button>
      {error ? <p className="error-line">{error}</p> : null}
      <p className="place-card-kicker">Annual Ground Rent</p>
      <h2 className="place-card-title">{title}</h2>
      <p className="location-line">
        {place.lat.toFixed(5)}, {place.lng.toFixed(5)}
      </p>
      {place.postcode ? (
        <p className="meta">Postcode: {place.postcode}</p>
      ) : null}
      {place.dataZoneCode ? (
        <>
          <p className="meta" data-testid="place-data-zone">
            Data zone: {place.dataZoneName || place.dataZoneCode}
            {place.dataZoneName && place.dataZoneCode
              ? ` (${place.dataZoneCode})`
              : null}
            {place.dataZoneVintage ? ` · ${place.dataZoneVintage}` : null}
          </p>
          {place.laName ? (
            <p className="meta" data-testid="place-la-name">
              Council: {place.laName}
            </p>
          ) : null}
          {place.population != null ? (
            <p className="meta" data-testid="place-population">
              Population: {formatCount(place.population)}
              {place.popYear ? ` (${place.popYear})` : null}
            </p>
          ) : null}
          {place.dwellings != null ? (
            <p className="meta" data-testid="place-dwellings">
              Dwellings: {formatCount(place.dwellings)}
              {place.dwYear ? ` (${place.dwYear})` : null}
            </p>
          ) : null}
        </>
      ) : loading ? (
        <p className="meta">Looking up this place…</p>
      ) : (
        <p className="meta">No data zone name for this point yet.</p>
      )}
      <section
        className="place-card-rent place-card-rent-stub"
        aria-label="Annual Ground Rent ranges"
        data-testid="place-stub-rent-ranges"
      >
        <p className="place-card-note">
          Scot-LAND&apos;s purpose is Annual Ground Rent. Rents appear only as
          ranges labelled market, proxy or shadow. £ figures are not published
          yet.
        </p>
        <ul className="place-rent-range-list">
          {PLACE_CARD_RENT_RANGE_TAGS.map((tag) => (
            <li
              key={tag}
              className={`place-rent-range-row tone-${tag}`}
              data-testid={`place-stub-rent-${tag}`}
            >
              <span className={`place-stack-tag tone-${tag}`}>{tag}</span>
              <span className="place-rent-range-label">not yet</span>
            </li>
          ))}
        </ul>
        <p
          className="place-card-grain"
          data-testid="place-stub-data-zone-grain"
        >
          {PLACE_CARD_DATA_ZONE_GRAIN}
        </p>
      </section>
      <p className="meta">
        <a href="/mission">Mission</a>
        {" · "}
        <a href="/methodology">Methodology</a>
      </p>
    </aside>
  );
}
