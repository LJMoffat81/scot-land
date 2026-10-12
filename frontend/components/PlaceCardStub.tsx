"use client";

export type PlaceStub = {
  lat: number;
  lng: number;
  label?: string | null;
  postcode?: string | null;
  dataZoneCode?: string | null;
  dataZoneName?: string | null;
};

type PlaceCardStubProps = {
  place: PlaceStub;
  loading?: boolean;
  error?: string | null;
  onClose: () => void;
};

/**
 * Lightweight place card for the public w3w-style shell.
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
        <p className="meta">
          Data zone: {place.dataZoneName || place.dataZoneCode}
          {place.dataZoneName && place.dataZoneCode
            ? ` (${place.dataZoneCode})`
            : null}
        </p>
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
        <a href="/methodology">About the method</a>
      </p>
    </aside>
  );
}
