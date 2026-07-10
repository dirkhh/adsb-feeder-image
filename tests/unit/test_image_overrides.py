"""
Tests for persistent container image override feature.

The override file ``/opt/adsb/config/docker.image.overrides`` lives in the
config directory so it persists across updates.  It contains KEY=VALUE
lines where KEY must match ``^[A-Z0-9_]+_CONTAINER$``.  Overrides are
applied after the vendor ``docker.image.versions`` defaults and before
any config.json or .env are written or a compose restart occurs.
"""
import os
import importlib
from pathlib import Path

import pytest

from utils.paths import DOCKER_IMAGE_OVERRIDES_FILE, DOCKER_IMAGE_VERSIONS_FILE
from utils.data import Data
from utils.environment import Env
from utils.config import (
    write_values_to_config_json,
    read_values_from_config_json,
    write_values_to_env_file,
    read_values_from_env_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def reset_data_singleton(clear_env: bool = False):
    """
    Reset Data singleton so every test gets a clean slate.

    If *clear_env* is True, also clear any container entries from the
    class-level ``_env`` set (the standard ``reset_for_testing()`` only
    re-reconciles them, it does not purge).
    """
    import utils.paths
    import utils.config
    importlib.reload(utils.paths)
    importlib.reload(utils.config)

    if clear_env:
        # Remove container entries accumulated from earlier tests.
        to_remove = [e for e in Data._env if "container" in e.tags]
        for e in to_remove:
            Data._env.discard(e)

    Data.reset_for_testing()


def write_override_file(overrides_path: Path, lines: list[str]) -> Path:
    """Write a docker.image.overrides file with the given lines."""
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text("\n".join(lines) + "\n")
    return overrides_path


def create_data_with_container_entries(container_entries: dict[str, str]) -> "Data":
    """
    Create a Data instance and manually add container Env entries to
    ``_env``.  In production these are loaded at class-body time from
    ``docker.image.versions``; in test we replicate that step.

    Also calls ``_apply_image_overrides`` so any override file present
    takes effect immediately.

    IMPORTANT: caller must have called ``reset_data_singleton(clear_env=True)``
    first to ensure ``_env`` does not leak container entries from previous
    tests.
    """
    # Start with an empty config so Env values write cleanly
    write_values_to_config_json({}, reason="test setup")

    data = Data()

    # __post_init__ on Data() calls _apply_image_overrides() — at this point
    # no container entries are in _env yet (they were cleared), so it's a no-op.

    for name, value in container_entries.items():
        # Do NOT pass ``value=`` to the constructor — that would set
        # ``_value`` immediately, making the later ``entry.value = value``
        # setter short-circuit (value == _value) and skip the _reconcile()
        # call that actually writes the key to config.json.
        entry = Env(name, tags=["container", "norestore"])
        entry.value = value  # Env setter writes to config.json
        data._env.add(entry)

    # Now that container entries exist in _env, apply overrides
    data._apply_image_overrides()
    return data


# ---------------------------------------------------------------------------
# Unit tests: override parsing & validation
# ---------------------------------------------------------------------------

class TestOverrideFileParsing:
    """Test the _apply_image_overrides method on Data instances."""

    def test_valid_override_applied(self, adsb_test_env):
        """A valid override line replaces the vendor container version."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:9.9.9-custom",
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        sky_env = data.env("SKYSTATS_CONTAINER")
        assert sky_env is not None
        assert sky_env.value == "ghcr.io/tomcarman/skystats:9.9.9-custom"

    def test_comment_and_blank_lines_ignored(self, adsb_test_env):
        """Comments and blank lines are skipped."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "# this is a comment",
            "",
            "   # indented comment",
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:9.9.9-override",
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        sky_env = data.env("SKYSTATS_CONTAINER")
        assert sky_env.value == "ghcr.io/tomcarman/skystats:9.9.9-override"

    def test_invalid_key_rejected(self, adsb_test_env):
        """Keys not matching ^[A-Z0-9_]+_CONTAINER$ are rejected."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "skystats_container=ghcr.io/tomcarman/skystats:evil",  # lowercase
            "INVALID_KEY=some_value",                               # no _CONTAINER suffix
            "SKY-STATS_CONTAINER=some_value",                       # contains dash
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        sky_env = data.env("SKYSTATS_CONTAINER")
        assert sky_env.value == "ghcr.io/tomcarman/skystats:0.1.13"

    def test_empty_value_rejected(self, adsb_test_env):
        """Keys with empty values are rejected."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER=",
            "SKYSTATS_CONTAINER=   ",
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        sky_env = data.env("SKYSTATS_CONTAINER")
        assert sky_env.value == "ghcr.io/tomcarman/skystats:0.1.13"

    def test_unknown_key_logged_but_not_crash(self, adsb_test_env):
        """Well-formed unknown key is logged without crashing."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "NONEXISTENT_CONTAINER=some/image:tag",
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        assert data.env("SKYSTATS_CONTAINER") is not None
        assert data.env("NONEXISTENT_CONTAINER") is None

    def test_no_override_file_is_noop(self, adsb_test_env):
        """No override file: no errors, vendor defaults remain."""
        reset_data_singleton(clear_env=True)

        if DOCKER_IMAGE_OVERRIDES_FILE.exists():
            DOCKER_IMAGE_OVERRIDES_FILE.unlink()

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        sky_env = data.env("SKYSTATS_CONTAINER")
        assert sky_env.value == "ghcr.io/tomcarman/skystats:0.1.13"

    def test_multiple_valid_overrides(self, adsb_test_env):
        """Multiple valid overrides are all applied."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:9.9.9-custom",
            "FR24_CONTAINER=myrepo/fr24:custom-tag",
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
            "FR24_CONTAINER": "ghcr.io/sdr-enthusiasts/docker-flightradar24:latest-build-850",
            "ULTRAFEEDER_CONTAINER": "ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest-build-931",
        })

        assert data.env("SKYSTATS_CONTAINER").value == "ghcr.io/tomcarman/skystats:9.9.9-custom"
        assert data.env("FR24_CONTAINER").value == "myrepo/fr24:custom-tag"
        assert data.env("ULTRAFEEDER_CONTAINER").value == "ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest-build-931"

    def test_override_key_no_equals_sign(self, adsb_test_env):
        """A line without '=' is rejected gracefully."""
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER",  # no '='
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        sky_env = data.env("SKYSTATS_CONTAINER")
        assert sky_env.value == "ghcr.io/tomcarman/skystats:0.1.13"


# ---------------------------------------------------------------------------
# Integration tests: overrides flow through to config.json and .env
# ---------------------------------------------------------------------------

class TestOverrideFlowToConfigFiles:
    """
    Prove that a vendor SKYSTATS_CONTAINER default is replaced by an override
    in both config.json and .env before the compose update boundary.
    """

    def test_override_appears_in_config_json(self, adsb_test_env):
        """
        Regression test: override value must appear in config.json.
        The Env setter writes to config.json immediately when an override is applied.
        """
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:9.9.9-custom",
        ])

        create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        config = read_values_from_config_json(no_cache=True)
        assert config.get("SKYSTATS_CONTAINER") == "ghcr.io/tomcarman/skystats:9.9.9-custom"

    def test_override_appears_in_env_file(self, adsb_test_env):
        """
        Regression test: override value must appear in the rendered .env file.
        Simulates the write_envfile() boundary before compose restart.
        """
        reset_data_singleton(clear_env=True)

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:9.9.9-custom",
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
        })

        write_values_to_env_file(data.envs_for_envfile)
        env_values = read_values_from_env_file()
        assert env_values.get("SKYSTATS_CONTAINER") == "ghcr.io/tomcarman/skystats:9.9.9-custom"

    def test_full_flow_vendor_default_replaced_before_compose_boundary(self, adsb_test_env):
        """
        End-to-end regression test: vendor SKYSTATS_CONTAINER default is
        replaced by an override in BOTH config.json AND .env, proving the
        override takes effect before any compose restart.
        """
        reset_data_singleton(clear_env=True)

        VENDOR_DEFAULT = "ghcr.io/tomcarman/skystats:0.1.13"
        OVERRIDE_VALUE = "my.registry.example.com/skystats:custom-v1.0.0"
        VENDOR_ULTRAFEEDER = "ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest-build-931"

        write_override_file(DOCKER_IMAGE_OVERRIDES_FILE, [
            "SKYSTATS_CONTAINER=" + OVERRIDE_VALUE,
        ])

        data = create_data_with_container_entries({
            "SKYSTATS_CONTAINER": VENDOR_DEFAULT,
            "ULTRAFEEDER_CONTAINER": VENDOR_ULTRAFEEDER,
        })

        # config.json must have the override
        config = read_values_from_config_json(no_cache=True)
        assert config.get("SKYSTATS_CONTAINER") == OVERRIDE_VALUE, (
            f"config.json: expected {OVERRIDE_VALUE}, got {config.get('SKYSTATS_CONTAINER')}"
        )

        # Write .env and check
        write_values_to_env_file(data.envs_for_envfile)
        env_values = read_values_from_env_file()
        assert env_values.get("SKYSTATS_CONTAINER") == OVERRIDE_VALUE, (
            f".env: expected {OVERRIDE_VALUE}, got {env_values.get('SKYSTATS_CONTAINER')}"
        )

        # Non-overridden container preserves vendor default
        assert env_values.get("ULTRAFEEDER_CONTAINER") == VENDOR_ULTRAFEEDER
        assert config.get("ULTRAFEEDER_CONTAINER") == VENDOR_ULTRAFEEDER
