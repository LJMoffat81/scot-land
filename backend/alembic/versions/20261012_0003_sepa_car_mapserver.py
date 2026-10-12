"""Recreate sepa_car_licences for MapServer 194/195 ingest.

Revision ID: 20261012_0003
Revises: 20261012_0002
Create Date: 2026-10-12
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20261012_0003"
down_revision: Union[str, None] = "20261012_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with backend/db/schema/006_hydro_sepa_car.sql (sepa_car_licences).
CREATE_SEPA_CAR = """
CREATE TABLE IF NOT EXISTS sepa_car_licences (
    authorisation_no TEXT NOT NULL,
    car_layer TEXT NOT NULL,
    authorisation_holder TEXT,
    authorisation_description TEXT,
    authorisation_level TEXT,
    authorisation_status TEXT,
    regulatory_area TEXT,
    authorisation_activity TEXT,
    category TEXT,
    ngr TEXT,
    easting INTEGER,
    northing INTEGER,
    commons_class TEXT NOT NULL DEFAULT 'extractive',
    value_tier TEXT NOT NULL DEFAULT 'market'
        CHECK (value_tier IN ('market', 'proxy', 'shadow')),
    publication_status TEXT NOT NULL DEFAULT 'ok'
        CHECK (publication_status IN ('ok', 'blocked')),
    geom GEOMETRY(Point, 4326),
    source TEXT NOT NULL DEFAULT 'SEPA_Reference MapServer CAR layers',
    licence TEXT NOT NULL DEFAULT 'OGL-3.0',
    retrieved_at DATE,
    PRIMARY KEY (authorisation_no, car_layer)
);

CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_geom
    ON sepa_car_licences USING GIST (geom)
    WHERE geom IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_level
    ON sepa_car_licences (authorisation_level);
CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_layer
    ON sepa_car_licences (car_layer);
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("DROP TABLE IF EXISTS sepa_car_licences CASCADE")
    op.get_bind().exec_driver_sql(CREATE_SEPA_CAR)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sepa_car_licences CASCADE")
    # Pre-MapServer CSV shape (revision 0002).
    op.get_bind().exec_driver_sql(
        """
        CREATE TABLE IF NOT EXISTS sepa_car_licences (
            authorisation_no TEXT PRIMARY KEY,
            authorisation_holder TEXT,
            authorisation_location TEXT,
            authorisation_level TEXT,
            authorisation_status TEXT,
            regulatory_area TEXT,
            authorisation_activity TEXT,
            ngr TEXT,
            geom GEOMETRY(Point, 4326),
            commons_class TEXT NOT NULL DEFAULT 'extractive',
            value_tier TEXT NOT NULL DEFAULT 'proxy',
            publication_status TEXT NOT NULL DEFAULT 'download_only',
            source TEXT NOT NULL DEFAULT 'SEPA Public Register CAR export',
            licence TEXT NOT NULL DEFAULT 'OGL-3.0',
            retrieved_at DATE
        );
        CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_geom
            ON sepa_car_licences USING GIST (geom)
            WHERE geom IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_sepa_car_licences_level
            ON sepa_car_licences (authorisation_level);
        """
    )
