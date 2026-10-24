#!/usr/bin/env python3
"""Regenerate synthetic SEA-EXTENT-2 MVT fixture (no real data)."""

from __future__ import annotations

from pathlib import Path

import mapbox_vector_tile

OUT = Path(__file__).resolve().parent


def main() -> None:
    raw = mapbox_vector_tile.encode(
        [
            {
                "name": "scotland-extent",
                "features": [
                    {
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [200, 200],
                                    [3800, 200],
                                    [3800, 3800],
                                    [200, 3800],
                                    [200, 200],
                                ]
                            ],
                        },
                        "properties": {"zone": "scotland"},
                        "id": 1,
                    }
                ],
            }
        ]
    )
    path = OUT / "scotland-extent.mvt"
    path.write_bytes(raw)
    if path.stat().st_size > 20_000:
        raise SystemExit(f"{path.name} exceeds 20 KB")
    print(f"{path.name}: {path.stat().st_size} B")


if __name__ == "__main__":
    main()
