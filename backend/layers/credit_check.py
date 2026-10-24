"""SRC-C CREDIT-1 — required credit phrase checker.

Reads ``data/config/credit_requirements.yaml`` and verifies each locator's
text contains every required phrase. Raises ``CreditError`` on the first
failure (sorted locator order).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REQUIREMENTS = REPO_ROOT / "data" / "config" / "credit_requirements.yaml"
REGISTRY_REL = Path("backend") / "layers" / "registry"
SOURCES_REL = Path("data") / "config" / "sources.yaml"


class CreditError(Exception):
    """Raised when a credit-requirements check fails (``CREDIT:`` prefix)."""


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "NoneType"
    return type(value).__name__


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_requirements(path: Path | str) -> dict:
    """Load and validate the top-level shape of a requirements YAML file."""
    p = Path(path)
    if not p.is_file():
        raise CreditError(f"CREDIT: requirements file not found: {p}")
    raw = p.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise CreditError(f"CREDIT: requirements not valid YAML: {p}") from exc
    if data is None:
        raise CreditError(f"CREDIT: requirements empty: {p}")
    if not isinstance(data, dict):
        raise CreditError(
            f"CREDIT: requirements must be a mapping, got {_type_name(data)}"
        )
    return data


def _phrases_for(locator: str, phrases: Any) -> list[str]:
    if (
        not isinstance(phrases, list)
        or len(phrases) == 0
        or any(not isinstance(p, str) for p in phrases)
    ):
        raise CreditError(
            f"CREDIT: {locator}: phrases must be a non-empty list of strings"
        )
    return phrases


def _registry_text(repo_root: Path, layer_id: str) -> str:
    path = repo_root / REGISTRY_REL / f"{layer_id}.yaml"
    if not path.is_file():
        raise CreditError(f"CREDIT: registry:{layer_id}: no such registry entry")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    attr = data.get("attribution")
    if not isinstance(attr, str):
        attr = ""
    return _norm_ws(attr)


def _sources_text(repo_root: Path, dotted: str) -> str:
    path = repo_root / SOURCES_REL
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise CreditError(f"CREDIT: sources:{dotted}: key not found")
        cur = cur[part]
    if not isinstance(cur, str):
        raise CreditError(
            f"CREDIT: sources:{dotted}: value must be a string, "
            f"got {_type_name(cur)}"
        )
    return _norm_ws(cur)


def _ts_regex_text(repo_root: Path, rest: str) -> str:
    if "::" not in rest:
        raise CreditError(f"CREDIT: ts_regex:{rest}: invalid locator")
    rel, pattern = rest.split("::", 1)
    path = repo_root / rel
    if not path.is_file():
        raise CreditError(f"CREDIT: ts_regex:{rel}: file not found")
    try:
        compiled = re.compile(pattern, re.DOTALL)
    except re.error as exc:
        raise CreditError(f"CREDIT: ts_regex:{rel}: invalid regex") from exc
    if compiled.groups != 1:
        raise CreditError(
            f"CREDIT: ts_regex:{rel}: regex must have exactly 1 group"
        )
    text = path.read_text(encoding="utf-8")
    matches = compiled.findall(text)
    if len(matches) != 1:
        raise CreditError(
            f"CREDIT: ts_regex:{rel}: expected 1 match, got {len(matches)}"
        )
    captured = matches[0]
    if isinstance(captured, tuple):
        captured = captured[0]
    return _norm_ws(str(captured))


def _resolve_text(locator: str, repo_root: Path) -> str:
    kind, _, rest = locator.partition(":")
    if kind == "registry":
        return _registry_text(repo_root, rest)
    if kind == "sources":
        return _sources_text(repo_root, rest)
    if kind == "ts_regex":
        return _ts_regex_text(repo_root, rest)
    raise CreditError(f"CREDIT: {locator}: unknown locator kind '{kind}'")


def check(reqs: dict, repo_root: Path | str) -> None:
    """Raise ``CreditError`` on the first failing locator (sorted order)."""
    root = Path(repo_root)
    for locator in sorted(reqs.keys()):
        phrases = _phrases_for(locator, reqs[locator])
        text = _resolve_text(str(locator), root)
        for phrase in phrases:
            if phrase not in text:
                raise CreditError(
                    f"CREDIT: {locator}: missing phrase '{phrase}'"
                )


def main(argv: list[str] | None = None) -> int:
    """CLI entry: print CreditError to stderr and return 1, else 0."""
    args = list(sys.argv[1:] if argv is None else argv)
    path = Path(args[0]) if args else DEFAULT_REQUIREMENTS
    try:
        reqs = load_requirements(path)
        check(reqs, REPO_ROOT)
    except CreditError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
