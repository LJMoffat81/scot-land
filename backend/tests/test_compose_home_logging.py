"""COMPOSE-LOGGING-3: json-file log rotation on the home compose stack.

Offline pin. Stdlib and PyYAML only; no application imports.
"""

from __future__ import annotations

import pathlib

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE_HOME = REPO_ROOT / "docker-compose.home.yml"

_FORBIDDEN_CAPS = ("cpus", "mem_limit", "mem_reservation", "memory")

_VALID_LOGGING = """\
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
"""


def collect_logging_violations(path: pathlib.Path) -> list[str]:
    if not path.is_file():
        return ["compose-logging-3: docker-compose.home.yml missing"]
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = document.get("services") if isinstance(document, dict) else None
    if not isinstance(services, dict) or not services:
        return ["compose-logging-3: docker-compose.home.yml has no services"]
    violations: list[str] = []
    for name, service in services.items():
        for cap in _FORBIDDEN_CAPS:
            if cap in service:
                violations.append(
                    f"compose-logging-3: service {name!r} has {cap} cap; caps are forbidden"
                )
        logging_block = service.get("logging")
        if not logging_block:
            violations.append(
                f"compose-logging-3: service {name!r} is missing logging"
            )
            continue
        driver = logging_block.get("driver")
        if driver != "json-file":
            violations.append(
                f"compose-logging-3: service {name!r} logging.driver is {driver!r}, expected 'json-file'"
            )
        options = logging_block.get("options") or {}
        max_size = options.get("max-size")
        if str(max_size) != "10m":
            violations.append(
                f"compose-logging-3: service {name!r} logging.options.max-size is {max_size!r}, expected '10m'"
            )
        max_file = options.get("max-file")
        if str(max_file) != "5":
            violations.append(
                f"compose-logging-3: service {name!r} logging.options.max-file is {max_file!r}, expected '5'"
            )
    return violations


def _write(tmp_path: pathlib.Path, text: str) -> pathlib.Path:
    path = tmp_path / "compose.yml"
    path.write_text(text, encoding="utf-8")
    return path


def test_home_compose_on_disk_has_json_file_rotation():
    violations = collect_logging_violations(COMPOSE_HOME)
    assert violations == [], "\n".join(violations)


def test_missing_logging_on_one_service(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "services:\n"
        "  db:\n"
        "    restart: unless-stopped\n"
        "  api:\n"
        f"{_VALID_LOGGING}"
        "  frontend:\n"
        f"{_VALID_LOGGING}",
    )
    assert collect_logging_violations(path) == [
        "compose-logging-3: service 'db' is missing logging"
    ]


def test_wrong_driver(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "services:\n"
        "  db:\n"
        "    logging:\n"
        "      driver: syslog\n"
        "      options:\n"
        '        max-size: "10m"\n'
        '        max-file: "5"\n'
        "  api:\n"
        f"{_VALID_LOGGING}"
        "  frontend:\n"
        f"{_VALID_LOGGING}",
    )
    assert collect_logging_violations(path) == [
        "compose-logging-3: service 'db' logging.driver is 'syslog', expected 'json-file'"
    ]


def test_wrong_max_size(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "services:\n"
        "  db:\n"
        "    logging:\n"
        "      driver: json-file\n"
        "      options:\n"
        '        max-size: "100m"\n'
        '        max-file: "5"\n'
        "  api:\n"
        f"{_VALID_LOGGING}"
        "  frontend:\n"
        f"{_VALID_LOGGING}",
    )
    assert collect_logging_violations(path) == [
        "compose-logging-3: service 'db' logging.options.max-size is '100m', expected '10m'"
    ]


def test_new_service_without_logging(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "services:\n"
        "  db:\n"
        f"{_VALID_LOGGING}"
        "  api:\n"
        f"{_VALID_LOGGING}"
        "  frontend:\n"
        f"{_VALID_LOGGING}"
        "  worker:\n"
        "    restart: unless-stopped\n",
    )
    assert collect_logging_violations(path) == [
        "compose-logging-3: service 'worker' is missing logging"
    ]


def test_compose_file_missing(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "does-not-exist.yml"
    assert collect_logging_violations(missing) == [
        "compose-logging-3: docker-compose.home.yml missing"
    ]


def test_wrong_max_file(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "services:\n"
        "  db:\n"
        "    logging:\n"
        "      driver: json-file\n"
        "      options:\n"
        '        max-size: "10m"\n'
        '        max-file: "20"\n'
        "  api:\n"
        f"{_VALID_LOGGING}"
        "  frontend:\n"
        f"{_VALID_LOGGING}",
    )
    assert collect_logging_violations(path) == [
        "compose-logging-3: service 'db' logging.options.max-file is '20', expected '5'"
    ]


def test_forbidden_cpu_cap(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "services:\n"
        "  db:\n"
        "    cpus: 1.0\n"
        f"{_VALID_LOGGING}"
        "  api:\n"
        f"{_VALID_LOGGING}"
        "  frontend:\n"
        f"{_VALID_LOGGING}",
    )
    assert collect_logging_violations(path) == [
        "compose-logging-3: service 'db' has cpus cap; caps are forbidden"
    ]


def test_anchor_fixture_resolves_to_no_violations(tmp_path: pathlib.Path) -> None:
    path = _write(
        tmp_path,
        "x-logging: &default-logging\n"
        "  driver: json-file\n"
        "  options:\n"
        '    max-size: "10m"\n'
        '    max-file: "5"\n'
        "services:\n"
        "  db:\n"
        "    logging: *default-logging\n"
        "  api:\n"
        "    logging: *default-logging\n"
        "  frontend:\n"
        "    logging: *default-logging\n",
    )
    assert collect_logging_violations(path) == []
