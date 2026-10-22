#!/usr/bin/env python3
"""Regenerate synthetic ARCH-2b MVT fixtures (no real data)."""

from __future__ import annotations

from pathlib import Path

import mapbox_vector_tile

OUT = Path(__file__).resolve().parent


def write(name: str, layer_name: str, features: list) -> None:
    raw = mapbox_vector_tile.encode([{"name": layer_name, "features": features}])
    path = OUT / name
    path.write_bytes(raw)
    if path.stat().st_size > 20_000:
        raise SystemExit(f"{name} exceeds 20 KB")
    print(f"{name}: {path.stat().st_size} B")


def main() -> None:
    write(
        "dz2022.mvt",
        "dz2022",
        [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [100, 100],
                            [3900, 100],
                            [3900, 3900],
                            [100, 3900],
                            [100, 100],
                        ]
                    ],
                },
                "properties": {"feature_id": "S01013482", "name": "Synthetic DZ"},
                "id": 1,
            }
        ],
    )
    write(
        "oil-fields.mvt",
        "oil-fields",
        [
            {
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [500, 500],
                            [2000, 500],
                            [2000, 2000],
                            [500, 2000],
                            [500, 500],
                        ]
                    ],
                },
                "properties": {
                    "feature_id": "field-1",
                    "FIELDNAME": "Synthetic Field",
                },
                "id": 1,
            }
        ],
    )
    write(
        "platforms.mvt",
        "platforms",
        [
            {
                "geometry": {"type": "Point", "coordinates": [2048, 2048]},
                "properties": {"feature_id": "plat-1", "NAME": "P1"},
                "id": 1,
            }
        ],
    )
    write(
        "pipelines.mvt",
        "pipelines",
        [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[200, 200], [3800, 3800]],
                },
                "properties": {"feature_id": "pipe-1", "PIPE_NAME": "P"},
                "id": 1,
            }
        ],
    )


if __name__ == "__main__":
    main()
