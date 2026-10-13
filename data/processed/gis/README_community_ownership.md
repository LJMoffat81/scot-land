# Community Ownership in Scotland 2024 (OGL map points)

Built for Scot-LAND map / PostGIS ingest. Does **not** write under `data/external`.

## Files

| File | Role |
|------|------|
| `community_ownership_assets.geojson` | 853 WGS84 points for PostGIS + map |
| `SOURCES_SHA256_community_ownership.txt` | SHA-256 of the SG Dataset XLSX |

Flat CSV with a `postcode` column is not tracked (public-repo personal-column guard).

## Source

| Field | Value |
|-------|--------|
| Publication | [Community Ownership in Scotland 2024](https://www.gov.scot/publications/community-ownership-in-scotland-2024/) |
| Dataset | Supporting document *Community Ownership in Scotland 2024 - Dataset* (Excel) |
| Licence | [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) |
| Vintage | As at December 2024 |
| Geometry | postcodes.io centroid of the published asset postcode — **not** a title polygon |

## Load

```bash
cd backend
export DATABASE_URL=postgresql://...
python -m etl.ingest_community_ownership --replace
```

API: `GET /layers/open/community-ownership` → **503** when the table is empty.

## Gaps (labelled in product)

- Points are postcode centroids, not title extents
- Some assets have no published area (Sasine)
- Confidential assets are excluded from the open dataset
- Spatial Hub Community Asset Transfer WFS stayed login-gated when checked — separate product, not mirrored
