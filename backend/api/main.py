"""Scot-LAND API entrypoint.

The Wealth routes (api/wealth_routes.py) always load. The legacy AGR router
(api/agr_routes.py) and the open-platform router (api/platform_routes.py) are
optional: if their imports fail, the failure is logged, reported on /health and
the router is skipped. Nothing is silently half-loaded.

    cd backend && uvicorn api.main:app
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cadastral_routes import router as cadastral_router
from api.common import _load_postcode_api_url, _scotland_bounds_check  # noqa: F401  (back-compat)
from api.cors import cors_settings
from api.internal_auth import ENV_TOKEN as INTERNAL_TOKEN_ENV, configured_token
from api.wealth_routes import router as wealth_router
from georgist.db import db_status
from georgist.publication_rules import check_router

logger = logging.getLogger("scot_land.api")

API_VERSION_FALLBACK = "wealth-api-boot"

# (module, attribute) of optional routers, in include order.
OPTIONAL_ROUTERS: tuple[tuple[str, str], ...] = (
    ("api.agr_routes", "router"),
    ("api.platform_routes", "router"),
)

ROUTER_STATUS: dict[str, dict[str, Any]] = {
    "api.wealth_routes": {"loaded": True},
    "api.cadastral_routes": {"loaded": True},
}


def _include_optional(app: FastAPI, module_name: str, attr: str) -> Any | None:
    try:
        module = importlib.import_module(module_name)
        router = getattr(module, attr)
        check_router(module_name, [p for _, p in registered_routes(router)])  # publication geometry rule
        app.include_router(router)
    except Exception as exc:  # ImportError, NameError, missing data at import, PublicationRuleError, ...
        logger.warning("Skipping %s: %s: %s", module_name, type(exc).__name__, exc)
        ROUTER_STATUS[module_name] = {"loaded": False, "error": f"{type(exc).__name__}: {exc}"}
        return None
    ROUTER_STATUS[module_name] = {"loaded": True}
    return module


def registered_routes(app_or_router: Any) -> list[tuple[str, str]]:
    """(method, path) for every HTTP route, walking included routers on any FastAPI version."""
    out: list[tuple[str, str]] = []
    for route in getattr(app_or_router, "routes", []):
        inner = getattr(route, "original_router", None)
        if inner is not None:  # FastAPI >= 0.13x lazily wraps included routers
            prefix = getattr(getattr(route, "include_context", None), "prefix", "") or ""
            out += [(m, prefix + p) for m, p in registered_routes(inner)]
            continue
        path = getattr(route, "path", None)
        for method in sorted(getattr(route, "methods", None) or ()):
            if path is not None:
                out.append((method, path))
    return out


def assert_no_duplicate_routes(app: FastAPI) -> None:
    seen: set[tuple[str, str]] = set()
    dupes = sorted({r for r in registered_routes(app) if r in seen or seen.add(r)})
    if dupes:
        raise RuntimeError(f"Duplicate routes registered: {dupes}")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Scot-LAND API",
        description=(
            "Scot-LAND National Wealth Engine (experimental research estimates) and, when "
            "its modules are present, the Annual Ground Rent assessment API."
        ),
        version=API_VERSION_FALLBACK,
    )
    origins, origin_regex = cors_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Core routers: an undeclared or illegal public route stops the app (publication geometry rule).
    check_router("api.wealth_routes", [p for _, p in registered_routes(wealth_router)])
    app.include_router(wealth_router)
    check_router("api.cadastral_routes", [p for _, p in registered_routes(cadastral_router)])
    app.include_router(cadastral_router)
    from api.geocode_routes import router as geocode_router  # noqa: PLC0415

    check_router("api.geocode_routes", [p for _, p in registered_routes(geocode_router)])
    app.include_router(geocode_router)
    from api import internal_routes  # noqa: PLC0415 (wealth-only deps)

    ROUTER_STATUS["api.internal_routes"] = {
        "loaded": False,
        "note": "set ENABLE_INTERNAL_ENDPOINTS=1 and INTERNAL_API_TOKEN (never fall open)",
    }
    if internal_routes.internal_enabled():
        app.include_router(internal_routes.router)
        token_ok = configured_token() is not None
        ROUTER_STATUS["api.internal_routes"] = {
            "loaded": True,
            "auth": "configured" if token_ok else "locked",
            "note": (
                "INTERNAL mounted; auth required (Bearer / X-API-Key)"
                if token_ok
                else f"INTERNAL mounted but locked: set {INTERNAL_TOKEN_ENV}"
            ),
        }
        if token_ok:
            logger.warning(
                "Internal endpoints enabled with auth: /internal/... requires %s",
                INTERNAL_TOKEN_ENV,
            )
        else:
            logger.warning(
                "Internal endpoints mounted but LOCKED: %s is unset (never fall open)",
                INTERNAL_TOKEN_ENV,
            )
    loaded = {name: _include_optional(app, name, attr) for name, attr in OPTIONAL_ROUTERS}
    agr = loaded.get("api.agr_routes")

    @app.get("/health")
    def health() -> dict:
        """Liveness plus honest dependency status. Never 500s; DB down is reported, not hidden."""
        body: dict[str, Any] = {
            "status": "ok",
            "service": "scot-land",
            "version": API_VERSION_FALLBACK,
            "git_commit": os.getenv("GIT_COMMIT") or None,
            "db": db_status(),
            "routers": ROUTER_STATUS,
        }
        if agr is not None:
            try:
                body.update(agr.agr_health_extras())
            except Exception as exc:
                body["agr_error"] = f"{type(exc).__name__}: {exc}"
        return body

    assert_no_duplicate_routes(app)
    check_router("app", [p for _, p in registered_routes(app)])  # belt and braces over every mounted route
    return app


app = create_app()
