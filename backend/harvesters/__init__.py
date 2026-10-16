"""LAYERS-ADD-1 harvesters (auto + manual_drop).

Manual-drop harvesters must never open HTTP, use AuthKeys, or automate
Spatial Hub login / terms acceptance (acceptance check L8).
"""

from __future__ import annotations

from harvesters.base import HarvesterResult, load_manual_drop, run_harvester

__all__ = ["HarvesterResult", "load_manual_drop", "run_harvester"]
