-- CLIP-VALID-1: rows that are still unusable after repair (fail closed).
SELECT feature_id
FROM __SRC__
WHERE NOT ST_IsValid(geom)
   OR ST_IsEmpty(geom)
   OR GeometryType(geom) NOT IN ('POLYGON', 'MULTIPOLYGON')
ORDER BY feature_id;
