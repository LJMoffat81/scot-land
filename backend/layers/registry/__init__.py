"""Config-driven layer registry (ARCH-1)."""

from __future__ import annotations

from layers.registry.loader import (
    LayerEntry,
    RegistryError,
    load_registry,
    registry,
)

__all__ = ["LayerEntry", "RegistryError", "load_registry", "registry"]
