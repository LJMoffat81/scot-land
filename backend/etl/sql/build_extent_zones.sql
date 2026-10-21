-- Build disjoint Scotland extent zones from staging parts (ARCH-1).
-- Expects temp tables:
--   tmp_extent_parts(zone text, geom geometry)
-- Writes:
--   ref.extent, ref.extent_sub, ref.extent_buf50_sub for geography='scotland'

CREATE SCHEMA IF NOT EXISTS ref;

CREATE TABLE IF NOT EXISTS ref.extent (
  geography text NOT NULL,
  zone text NOT NULL,
  geom geometry(MultiPolygon, 27700) NOT NULL,
  sha256 text NOT NULL,
  built_at timestamptz NOT NULL,
  PRIMARY KEY (geography, zone)
);

CREATE TABLE IF NOT EXISTS ref.extent_sub (
  geography text NOT NULL,
  zone text NOT NULL,
  geom geometry(MultiPolygon, 27700) NOT NULL
);

CREATE TABLE IF NOT EXISTS ref.extent_buf50_sub (
  geography text NOT NULL,
  geom geometry(MultiPolygon, 27700) NOT NULL
);

CREATE INDEX IF NOT EXISTS extent_sub_geom_idx
  ON ref.extent_sub USING GIST (geom);

CREATE INDEX IF NOT EXISTS extent_buf50_sub_geom_idx
  ON ref.extent_buf50_sub USING GIST (geom);

-- Per-part sliver close, then union per zone.
-- Temp tables are session-scoped (no ON COMMIT DROP) so the Python driver can
-- read stats and persist ref.* after this script.
CREATE TEMP TABLE tmp_extent_union AS
SELECT
  zone,
  ST_Multi(
    ST_CollectionExtract(
      ST_MakeValid(
        ST_Union(ref.close_slivers(geom))
      ),
      3
    )
  ) AS geom
FROM tmp_extent_parts
GROUP BY zone;

-- Disjoint zones: inshore − land; offshore − (land ∪ inshore).
CREATE TEMP TABLE tmp_extent_disjoint AS
WITH land AS (
  SELECT geom FROM tmp_extent_union WHERE zone = 'land'
),
inshore_raw AS (
  SELECT geom FROM tmp_extent_union WHERE zone = 'inshore_0_12nm'
),
offshore_raw AS (
  SELECT geom FROM tmp_extent_union WHERE zone = 'offshore_12_200nm'
),
inshore AS (
  SELECT ST_Multi(
    ST_CollectionExtract(
      ST_MakeValid(ST_Difference(i.geom, l.geom)),
      3
    )
  ) AS geom
  FROM inshore_raw i, land l
),
offshore AS (
  SELECT ST_Multi(
    ST_CollectionExtract(
      ST_MakeValid(
        ST_Difference(
          o.geom,
          ST_Union(l.geom, i.geom)
        )
      ),
      3
    )
  ) AS geom
  FROM offshore_raw o, land l, inshore i
)
SELECT 'land'::text AS zone, geom FROM land
UNION ALL
SELECT 'inshore_0_12nm', geom FROM inshore
UNION ALL
SELECT 'offshore_12_200nm', geom FROM offshore;

-- Simplify-preserve-topology 25 m, make valid, areal extract, multi.
CREATE TEMP TABLE tmp_extent_final AS
SELECT
  zone,
  ST_Multi(
    ST_CollectionExtract(
      ST_MakeValid(
        ST_SimplifyPreserveTopology(geom, 25.0)
      ),
      3
    )
  ) AS geom
FROM tmp_extent_disjoint;
