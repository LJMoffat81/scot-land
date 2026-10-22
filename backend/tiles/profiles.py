"""tippecanoe flag profiles keyed by ``zoom.low_zoom`` (ARCH-2a)."""

from __future__ import annotations


class ProfileError(Exception):
    """Raised when a low_zoom profile cannot be built yet."""


def tippecanoe_flags(low_zoom: str, *, zoom_max: int, keep_fields: list[str]) -> list[str]:
    """Return tippecanoe argv flags for the given ``low_zoom`` profile."""
    if low_zoom == "keep_all":
        return [
            "--no-feature-limit",
            "--no-tile-size-limit",
            "--no-tiny-polygon-reduction",
            "--detect-shared-borders",
        ]
    if low_zoom == "simplify":
        return [
            "--no-feature-limit",
            "--no-tile-size-limit",
            "--no-tiny-polygon-reduction",
            "--detect-shared-borders",
        ]
    if low_zoom == "cluster":
        first = keep_fields[0] if keep_fields else "feature_id"
        return [
            "-r1",
            "--cluster-distance=10",
            f"--cluster-maxzoom={zoom_max - 1}",
            f"--accumulate-attribute={first}:comma",
            "--no-feature-limit",
            "--no-tile-size-limit",
        ]
    if low_zoom == "coalesce":
        return ["--coalesce-densest-as-needed"]
    if low_zoom.startswith("aggregate:"):
        raise ProfileError(
            f"low_zoom {low_zoom} not built until ARCH-4a"
        )
    raise ProfileError(f"low_zoom {low_zoom} not built until ARCH-4a")
