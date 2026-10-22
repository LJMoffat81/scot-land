-- CLIP-VALID-1: repair invalid polygon geometries in the stage table before clip.
-- Placeholders: __SRC__ stage table, __DIM__ declared CollectionExtract dimension (3).
-- Valid rows are not touched (WHERE NOT ST_IsValid), so their WKB is byte-identical.
UPDATE __SRC__
SET geom = ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), __DIM__))
WHERE NOT ST_IsValid(geom)
RETURNING feature_id;
