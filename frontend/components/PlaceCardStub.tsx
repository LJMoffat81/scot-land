"use client";

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
 * Lightweight place card for the public Scot-LAND squares shell.
 * No modelled AGR £, Surface Rent, or tax scenarios — those stay for later phases / HOLD PRs.
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
      <p className="place-card-kicker">Place</p>
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
      <p className="place-card-note">
        Ownership, vacant-land flags and research land-rent figures for this
        place will appear here later. Modelled Annual Ground Rent and tax
        scenarios are not shown on the public map yet.
      </p>
      <p className="meta">
        <a href="/mission">Mission</a>
        {" · "}
        <a href="/methodology">Methodology</a>
      </p>
    </aside>
  );
}
