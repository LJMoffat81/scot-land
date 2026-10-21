-- Close sub-metre slivers per part before zone union (ARCH-1).
-- Applied as ST_Buffer(+1) then ST_Buffer(-1) after ST_MakeValid.

CREATE SCHEMA IF NOT EXISTS ref;

CREATE OR REPLACE FUNCTION ref.close_slivers(g geometry)
RETURNS geometry
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
  SELECT CASE
    WHEN g IS NULL THEN NULL
    ELSE ST_Multi(
      ST_CollectionExtract(
        ST_MakeValid(
          ST_Buffer(ST_Buffer(ST_MakeValid(g), 1.0), -1.0)
        ),
        3
      )
    )
  END;
$$;
