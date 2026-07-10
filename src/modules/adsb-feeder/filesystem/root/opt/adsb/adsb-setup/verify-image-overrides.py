#!/usr/bin/env python3
"""
Strict verifier for persistent container image overrides.

Parses ``/opt/adsb/config/docker.image.overrides`` with the same key/value
rules used by ``Data._apply_image_overrides()`` and then **fails nonzero** on
any malformed, unknown, or empty entry.  Additionally, it reads the rendered
``config.json`` and ``.env`` files and verifies that every override is
exactly reflected in both.  Any mismatch causes a nonzero exit.

This is designed to be called from ``feeder-update`` **after**
``app.py --update-config`` and **immediately before**
``/opt/adsb/docker-update-adsb-im``, so that a broken or inconsistent
override set cannot reach the compose/image-update boundary.

Can also be imported and called with ``strict=False`` for warning-only
mode from initial-install contexts (pre-start / create-json).
"""

import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants matching the existing validation regex
# ---------------------------------------------------------------------------

_OVERRIDE_KEY_RE = re.compile(r"^[A-Z0-9_]+_CONTAINER$")


# ---------------------------------------------------------------------------
# Paths — resolved relative to ADSB_BASE_DIR so this script works both from
# /opt/adsb/adsb-setup/ (production) and from a test sandbox.
# ---------------------------------------------------------------------------


def _adsb_base() -> Path:
    """Return the ADS-B base directory (configurable via ADSB_BASE_DIR env)."""
    return Path(os.environ.get("ADSB_BASE_DIR", "/opt/adsb"))


def _override_file() -> Path:
    return _adsb_base() / "config" / "docker.image.overrides"


def _versions_file() -> Path:
    return _adsb_base() / "docker.image.versions"


def _config_json() -> Path:
    return _adsb_base() / "config" / "config.json"


def _env_file() -> Path:
    return _adsb_base() / "config" / ".env"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_overrides(path: Path) -> dict[str, str]:
    """
    Parse a docker.image.overrides file.

    Returns a dict of ``{KEY: value}``.

    Raises ``ValueError`` for malformed lines, invalid keys, or empty values.
    Unknown keys are *returned* in the dict (the caller decides whether to
    reject them).
    """
    overrides: dict[str, str] = {}

    with open(path, "r") as f:
        for line_num, line in enumerate(f, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if "=" not in stripped:
                raise ValueError(
                    f"docker.image.overrides line {line_num}: "
                    f"malformed line (no '='): {stripped}"
                )

            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()

            if not value:
                raise ValueError(
                    f"docker.image.overrides line {line_num}: "
                    f"empty value for key '{key}'"
                )

            if not _OVERRIDE_KEY_RE.match(key):
                raise ValueError(
                    f"docker.image.overrides line {line_num}: "
                    f"invalid key '{key}' — must match uppercase letters, "
                    f"digits, underscore and end with _CONTAINER"
                )

            overrides[key] = value

    return overrides


def _parse_versions(path: Path) -> set[str]:
    """
    Parse docker.image.versions and return the set of valid container keys.
    """
    keys: set[str] = set()
    with open(path, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key = stripped.partition("=")[0].strip()
                if key:
                    keys.add(key)
    return keys


def _read_config_json(path: Path) -> dict[str, str]:
    """Read config.json and return a flat dict of string values."""
    import json
    if not path.exists():
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    return {k: str(v) for k, v in data.items() if v is not None}


def _read_env_file(path: Path) -> dict[str, str]:
    """Read .env file and return a dict of KEY=VALUE pairs."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    with open(path, "r") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, value = stripped.partition("=")
                result[key.strip()] = value.strip()
    return result


# ---------------------------------------------------------------------------
# Main verification logic
# ---------------------------------------------------------------------------


def verify_image_overrides(strict: bool = True) -> bool:
    """
    Verify that the overrides file (if present) is well-formed and that every
    override is correctly reflected in config.json and .env.

    Args:
        strict: If ``True`` (default), unknown keys are treated as fatal
                errors.  Set to ``False`` to warn but not fail on unknown
                keys (useful during initial install when config.json/.env
                may not yet exist or be fully populated).

    Returns:
        ``True`` if verification passes (or no override file exists),
        ``False`` if any check fails.

    Raises:
        SystemExit(1) when called from CLI (via ``main()``) and verification
        fails.  When called as a library function, only returns ``False``.
    """
    override_path = _override_file()

    # No override file → nothing to verify → pass
    if not override_path.exists():
        return True

    errors: list[str] = []

    # --- Phase 1: parse and validate the override file itself ---

    try:
        overrides = _parse_overrides(override_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return False

    if not overrides:
        # File exists but contains no valid overrides (all comments/blank)
        return True

    # --- Phase 2: check all keys are known in docker.image.versions ---

    versions_path = _versions_file()
    known_keys: set[str] = set()
    if versions_path.exists():
        known_keys = _parse_versions(versions_path)

    for key in list(overrides.keys()):
        if key not in known_keys:
            msg = (
                f"ERROR: docker.image.overrides contains unknown key "
                f"'{key}' — not found in docker.image.versions"
            )
            if strict:
                errors.append(msg)
            else:
                print(f"WARNING: {msg}", file=sys.stderr)
                # In non-strict mode, remove unknown keys so they don't
                # cause spurious config.json/.env mismatch errors below.
                del overrides[key]

    # --- Phase 3: verify every override is in config.json ---

    config = _read_config_json(_config_json())
    for key, expected in overrides.items():
        actual = config.get(key)
        if actual is None:
            errors.append(
                f"ERROR: override key '{key}={expected}' is missing from config.json"
            )
        elif actual != expected:
            errors.append(
                f"ERROR: override key '{key}' mismatch in config.json — "
                f"expected '{expected}', got '{actual}'"
            )

    # --- Phase 4: verify every override is in .env ---

    env_values = _read_env_file(_env_file())
    for key, expected in overrides.items():
        actual = env_values.get(key)
        if actual is None:
            errors.append(
                f"ERROR: override key '{key}={expected}' is missing from .env"
            )
        elif actual != expected:
            errors.append(
                f"ERROR: override key '{key}' mismatch in .env — "
                f"expected '{expected}', got '{actual}'"
            )

    # --- Report ---

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return False

    return True


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point.  Exits 0 on success, 1 on failure."""
    strict = "--no-strict" not in sys.argv
    ok = verify_image_overrides(strict=strict)
    if not ok:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
