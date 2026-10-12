"""Route registration: Wealth works without AGR, nothing is registered twice."""

import ast
from collections import Counter
from pathlib import Path

from api.main import ROUTER_STATUS, app, assert_no_duplicate_routes, registered_routes

API_DIR = Path(__file__).resolve().parents[2] / "api"
WEALTH_PATHS = {
    "/health",
    "/georgist/wealth",
    "/layers/georgist/surface-rent",
    "/layers/georgist/resource-rent",
    "/layers/georgist/eco-rent",
}


def _decorated_paths(path: Path) -> list[tuple[str, str]]:
    """(METHOD, path) from @app.get/@router.post(...) decorators in a source file."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in {"get", "post", "put", "delete", "patch"}
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    out.append((dec.func.attr.upper(), dec.args[0].value))
    return out


def test_app_imports_and_wealth_routes_registered():
    paths = {p for _, p in registered_routes(app)}
    assert WEALTH_PATHS <= paths
    assert ROUTER_STATUS["api.wealth_routes"]["loaded"] is True


def test_optional_routers_report_status_not_crash():
    for name in ("api.agr_routes", "api.platform_routes"):
        status = ROUTER_STATUS[name]
        assert "loaded" in status
        if not status["loaded"]:
            assert status["error"]  # skipped with a logged reason


def test_no_duplicate_routes_in_running_app():
    routes = registered_routes(app)
    dupes = [r for r, n in Counter(routes).items() if n > 1]
    assert dupes == []
    assert_no_duplicate_routes(app)


def test_no_duplicate_routes_across_all_router_sources():
    """Covers routers that are skipped today (AGR) so a restore cannot collide."""
    all_routes = []
    for src in sorted(API_DIR.glob("*.py")):
        all_routes += _decorated_paths(src)
    dupes = [r for r, n in Counter(all_routes).items() if n > 1]
    assert dupes == [], dupes


def test_surface_rent_route_defined_once():
    hits = [
        src.name
        for src in API_DIR.glob("*.py")
        for _, p in _decorated_paths(src)
        if p == "/layers/georgist/surface-rent"
    ]
    assert hits == ["wealth_routes.py"]


def test_wealth_router_does_not_import_agr():
    tree = ast.parse((API_DIR / "wealth_routes.py").read_text(encoding="utf-8"))
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m.split(".")[0] in {"agr", "layers", "validation", "spatial"} for m in mods), mods


def test_duplicate_guard_raises():
    import pytest
    from fastapi import APIRouter, FastAPI

    a = FastAPI()
    r = APIRouter()

    @r.get("/x")
    def one():
        return 1

    @a.get("/x")
    def two():
        return 2

    a.include_router(r)
    with pytest.raises(RuntimeError, match="Duplicate routes"):
        assert_no_duplicate_routes(a)
