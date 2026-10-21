-- Count features in __DST__ that fall outside the Scotland+50 m buffer.
-- A feature is inside if any buf50 part covers it, or the union of
-- overlapping buf50 parts covers it. Must return 0 after a successful clip.

SELECT count(*)::bigint AS outside_n
FROM __DST__ l
WHERE NOT EXISTS (
  SELECT 1
  FROM ref.extent_buf50_sub b
  WHERE b.geography = 'scotland'
    AND ST_Covers(b.geom, l.geom)
)
AND NOT ST_Covers(
  COALESCE(
    (
      SELECT ST_Union(b.geom)
      FROM ref.extent_buf50_sub b
      WHERE b.geography = 'scotland'
        AND b.geom && l.geom
    ),
    ST_GeomFromText('POLYGON EMPTY', 27700)
  ),
  l.geom
);
