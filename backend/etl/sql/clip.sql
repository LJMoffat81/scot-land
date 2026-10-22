-- Clip stage features to Scotland extent_sub parts for the requested zones.
-- Placeholders (substituted by run_layer, never user input):
--   __SRC__   stage table (schema-qualified, quoted)
--   __DST__   destination table (schema-qualified, quoted)
--   __ZONES__ SQL array literal e.g. ARRAY['land','inshore_0_12nm']::text[]
--   __DIM__   CollectionExtract dimension: 1=point 2=line 3=polygon
--   __IS_POINT__ true for point layers (intersects-only; no geometry rewrite)
--
-- Fast path: ST_Covers by any single sub part keeps the geometry unchanged
-- (no ST_Intersection). Slow path unions candidate parts then intersects.
-- Empty results are dropped. Properties / feature_id columns are preserved.

DROP TABLE IF EXISTS __DST__;

CREATE TABLE __DST__ AS
WITH candidates AS (
  SELECT
    s.*,
    EXISTS (
      SELECT 1
      FROM ref.extent_sub e
      WHERE e.geography = 'scotland'
        AND e.zone = ANY (__ZONES__)
        AND ST_Covers(e.geom, s.geom)
    ) AS fully_inside
  FROM __SRC__ s
  WHERE EXISTS (
    SELECT 1
    FROM ref.extent_sub e
    WHERE e.geography = 'scotland'
      AND e.zone = ANY (__ZONES__)
      AND e.geom && s.geom
      AND ST_Intersects(e.geom, s.geom)
  )
),
clipped AS (
  SELECT
    c.*,
    CASE
      WHEN __IS_POINT__ OR c.fully_inside THEN c.geom
      ELSE (
        SELECT ST_CollectionExtract(
          ST_MakeValid(
            ref.counted_intersection(
              c.geom,
              ST_Union(e.geom)
            )
          ),
          __DIM__
        )
        FROM ref.extent_sub e
        WHERE e.geography = 'scotland'
          AND e.zone = ANY (__ZONES__)
          AND e.geom && c.geom
          AND ST_Intersects(e.geom, c.geom)
      )
    END AS clip_geom
  FROM candidates c
)
SELECT
  feature_id,
  props,
  clip_geom AS geom,
  source_layer_ids,
  dataset_version,
  as_of,
  method,
  child_unit_ids
FROM clipped
WHERE clip_geom IS NOT NULL
  AND NOT ST_IsEmpty(clip_geom);
