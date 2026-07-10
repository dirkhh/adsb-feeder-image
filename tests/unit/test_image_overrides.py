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



# ---------------------------------------------------------------------------
# Verifier tests: prove the verify-image-overrides helper catches all
# failure modes and never lets a mismatch reach the docker-update boundary.
# ---------------------------------------------------------------------------

# Dynamic import helper for verify-image-overrides (hyphens in name prevent
# top-level ``import``; importlib handles it correctly)
def _get_vero():
    import importlib
    return importlib.import_module("verify-image-overrides")


class TestVerifyOverridesParser:
    """Unit tests for the verifier's own parsing logic (not the Data class)."""

    def test_parse_valid_overrides(self, adsb_test_env, tmp_path):
        """Valid overrides are parsed correctly."""
        vero = _get_vero()
        ov_path = tmp_path / "docker.image.overrides"
        ov_path.write_text(
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n"
            "FR24_CONTAINER=myreg/fr24:v2\n"
        )
        result = vero._parse_overrides(ov_path)
        assert result == {
            "SKYSTATS_CONTAINER": "myreg/skystats:v1",
            "FR24_CONTAINER": "myreg/fr24:v2",
        }

    def test_parse_malformed_no_equals(self, tmp_path):
        """Lines without '=' raise ValueError."""
        vero = _get_vero()
        ov_path = tmp_path / "docker.image.overrides"
        ov_path.write_text("SKYSTATS_CONTAINER\n")
        with pytest.raises(ValueError, match="malformed line"):
            vero._parse_overrides(ov_path)

    def test_parse_empty_value_raises(self, tmp_path):
        """Empty values raise ValueError."""
        vero = _get_vero()
        ov_path = tmp_path / "docker.image.overrides"
        ov_path.write_text("SKYSTATS_CONTAINER=\n")
        with pytest.raises(ValueError, match="empty value"):
            vero._parse_overrides(ov_path)

    def test_parse_invalid_key_raises(self, tmp_path):
        """Invalid keys (lowercase, dashes, no _CONTAINER suffix) raise ValueError."""
        vero = _get_vero()
        ov_path = tmp_path / "docker.image.overrides"
        ov_path.write_text("skystats_container=some/image:v1\n")
        with pytest.raises(ValueError, match="invalid key"):
            vero._parse_overrides(ov_path)

    def test_parse_blank_value_raises(self, tmp_path):
        """Whitespace-only values raise ValueError."""
        vero = _get_vero()
        ov_path = tmp_path / "docker.image.overrides"
        ov_path.write_text("SKYSTATS_CONTAINER=   \n")
        with pytest.raises(ValueError, match="empty value"):
            vero._parse_overrides(ov_path)

    def test_parse_comments_and_blanks_ignored(self, tmp_path):
        """Comments and blanks are properly skipped."""
        vero = _get_vero()
        ov_path = tmp_path / "docker.image.overrides"
        ov_path.write_text(
            "# a comment\n"
            "\n"
            "  # indented comment\n"
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n"
        )
        result = vero._parse_overrides(ov_path)
        assert result == {"SKYSTATS_CONTAINER": "myreg/skystats:v1"}


class TestVerifyOverridesIntegration:
    """Integration tests: verifier against config.json and .env."""

    def _setup_env(self, adsb_test_env, overrides_lines, config_data, env_data):
        """Create overrides, config.json, and .env for verification testing."""
        from utils.config import write_values_to_config_json, write_values_to_env_file
        vero = _get_vero()

        # Write the override file
        ov_path = vero._override_file()
        ov_path.parent.mkdir(parents=True, exist_ok=True)
        ov_path.write_text(overrides_lines)

        # Ensure docker.image.versions exists with matching keys
        ver_path = vero._versions_file()
        ver_path.write_text(
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:0.1.13\n"
            "FR24_CONTAINER=ghcr.io/sdr-enthusiasts/docker-flightradar24:latest-build-850\n"
            "ULTRAFEEDER_CONTAINER=ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest-build-931\n"
        )

        write_values_to_config_json(config_data, reason="test setup")
        write_values_to_env_file(env_data)

    def test_valid_overrides_pass_verification(self, adsb_test_env):
        """Well-formed overrides that match config.json and .env pass."""
        vero = _get_vero()
        self._setup_env(
            adsb_test_env,
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n",
            {"SKYSTATS_CONTAINER": "myreg/skystats:v1"},
            {"SKYSTATS_CONTAINER": "myreg/skystats:v1"},
        )
        assert vero.verify_image_overrides(strict=True) is True

    def test_bogus_override_key_fails_verification(self, adsb_test_env):
        """A line without '=' makes the verifier return False (fail-open prevention)."""
        vero = _get_vero()
        ov_path = vero._override_file()
        ov_path.parent.mkdir(parents=True, exist_ok=True)
        ov_path.write_text("SKYSTATS_CONTAINER\n")  # no '='
        # Ensure versions file exists so the verifier doesn't fail early
        ver_path = vero._versions_file()
        ver_path.write_text("SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:0.1.13\n")
        result = vero.verify_image_overrides(strict=True)
        assert result is False, "Malformed override must fail verification"

    def test_override_unknown_key_fails_strict(self, adsb_test_env):
        """Unknown keys cause strict verification to fail."""
        vero = _get_vero()
        self._setup_env(
            adsb_test_env,
            "NONEXISTENT_CONTAINER=some/image:tag\n",
            {"NONEXISTENT_CONTAINER": "some/image:tag"},
            {"NONEXISTENT_CONTAINER": "some/image:tag"},
        )
        result = vero.verify_image_overrides(strict=True)
        assert result is False, "Unknown key must fail strict verification"

    def test_override_unknown_key_passes_nonstrict(self, adsb_test_env):
        """Unknown keys are warned but do not fail in non-strict mode."""
        vero = _get_vero()
        self._setup_env(
            adsb_test_env,
            "NONEXISTENT_CONTAINER=some/image:tag\n",
            {},
            {},
        )
        result = vero.verify_image_overrides(strict=False)
        assert result is True, "Unknown key should be warned but not fail in non-strict"

    def test_config_json_mismatch_fails(self, adsb_test_env):
        """Override value not reflected in config.json -> verification fails."""
        vero = _get_vero()
        self._setup_env(
            adsb_test_env,
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n",
            {"SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13"},  # vendor default, wrong
            {"SKYSTATS_CONTAINER": "myreg/skystats:v1"},  # .env is correct
        )
        result = vero.verify_image_overrides(strict=True)
        assert result is False, "config.json mismatch must fail verification"

    def test_env_file_mismatch_fails(self, adsb_test_env):
        """Override value not reflected in .env -> verification fails."""
        vero = _get_vero()
        self._setup_env(
            adsb_test_env,
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n",
            {"SKYSTATS_CONTAINER": "myreg/skystats:v1"},  # config.json correct
            {"SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13"},  # .env wrong
        )
        result = vero.verify_image_overrides(strict=True)
        assert result is False, ".env mismatch must fail verification"

    def test_missing_from_both_fails(self, adsb_test_env):
        """Override present in file but missing from both config.json and .env -> fail."""
        vero = _get_vero()
        self._setup_env(
            adsb_test_env,
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n",
            {},  # config.json has no SKYSTATS_CONTAINER
            {},  # .env has no SKYSTATS_CONTAINER
        )
        result = vero.verify_image_overrides(strict=True)
        assert result is False, "Missing from both config.json and .env must fail"

    def test_no_override_file_passes(self, adsb_test_env):
        """No override file -> verification passes trivially."""
        vero = _get_vero()
        ov_path = vero._override_file()
        if ov_path.exists():
            ov_path.unlink()
        result = vero.verify_image_overrides(strict=True)
        assert result is True

    def test_empty_override_file_passes(self, adsb_test_env):
        """All-comments/blank override file passes."""
        vero = _get_vero()
        ov_path = vero._override_file()
        ov_path.parent.mkdir(parents=True, exist_ok=True)
        ov_path.write_text("# just a comment\n\n")
        result = vero.verify_image_overrides(strict=True)
        assert result is True


# ---------------------------------------------------------------------------
# Docker-update boundary tests: simulate the feeder-update script flow
# ---------------------------------------------------------------------------

class TestDockerUpdateBoundary:
    """
    Simulate the feeder-update boundary:

    1. app.py --update-config runs -> applies overrides -> writes config.json/.env
    2. Verify overrides (simulated by verify_image_overrides)
    3. docker-update-adsb-im (mocked)

    These tests prove that invalid overrides or mismatches prevent reaching
    the mocked docker-update boundary, while valid overrides allow it.
    """

    def _simulate_update_flow(self, adsb_test_env, overrides_lines):
        """
        Run the full simulated update flow and return True if
        docker-update-adsb-im was reached.

        This mirrors what feeder-update does:
          1. app.py --update-config  (simulated via Data + overrides)
          2. verify-image-overrides.py (called explicitly)
          3. /opt/adsb/docker-update-adsb-im (mocked -- we just record "reached")
        """
        from utils.config import write_values_to_config_json, write_values_to_env_file
        vero = _get_vero()

        # --- Step 1: simulate app.py --update-config ---
        reset_data_singleton(clear_env=True)

        ov_path = vero._override_file()
        ov_path.parent.mkdir(parents=True, exist_ok=True)
        ov_path.write_text(overrides_lines)

        # Ensure docker.image.versions exists
        ver_path = vero._versions_file()
        ver_path.write_text(
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:0.1.13\n"
            "FR24_CONTAINER=ghcr.io/sdr-enthusiasts/docker-flightradar24:latest-build-850\n"
        )

        write_values_to_config_json({}, reason="simulated update start")

        data = Data()
        # Manually seed container entries (as Data() would from docker.image.versions)
        for name, value in {
            "SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13",
            "FR24_CONTAINER": "ghcr.io/sdr-enthusiasts/docker-flightradar24:latest-build-850",
        }.items():
            entry = Env(name, tags=["container", "norestore"])
            entry.value = value
            data._env.add(entry)

        data._apply_image_overrides()
        write_values_to_env_file(data.envs_for_envfile)

        # --- Step 2: verify overrides (simulate feeder-update call) ---
        verified = vero.verify_image_overrides(strict=True)

        if not verified:
            # feeder-update would exit_with_message here -- abort
            return {"reached_docker_update": False, "reason": "verification failed"}

        # --- Step 3: docker-update-adsb-im (mocked) ---
        return {"reached_docker_update": True, "reason": "all checks passed"}

    def test_valid_overrides_reach_docker_update_boundary(self, adsb_test_env):
        """Valid matching overrides allow reaching the docker-update boundary."""
        result = self._simulate_update_flow(
            adsb_test_env,
            "SKYSTATS_CONTAINER=myreg/skystats:v1\n",
        )
        assert result["reached_docker_update"] is True, (
            f"Should reach docker-update, got: {result}"
        )

    def test_invalid_override_prevents_docker_update(self, adsb_test_env):
        """
        Regression test: a malformed override (no '=') must prevent
        reaching the docker-update boundary.
        """
        result = self._simulate_update_flow(
            adsb_test_env,
            "SKYSTATS_CONTAINER\n",  # no '=' -- malformed
        )
        assert result["reached_docker_update"] is False, (
            "Malformed override must abort before docker-update"
        )

    def test_override_mismatch_prevents_docker_update(self, adsb_test_env):
        """
        Regression test: an override that fails to render into config.json
        must prevent reaching the docker-update boundary.
        """
        # Write override BEFORE the Data simulation but sabotage
        # config.json/.env with wrong values to simulate a mismatch
        vero = _get_vero()
        from utils.config import write_values_to_config_json, write_values_to_env_file

        reset_data_singleton(clear_env=True)

        ov_path = vero._override_file()
        ov_path.parent.mkdir(parents=True, exist_ok=True)
        ov_path.write_text("SKYSTATS_CONTAINER=myreg/skystats:v1\n")

        ver_path = vero._versions_file()
        ver_path.write_text(
            "SKYSTATS_CONTAINER=ghcr.io/tomcarman/skystats:0.1.13\n"
        )

        write_values_to_config_json({}, reason="simulated update start")

        data = Data()
        entry = Env("SKYSTATS_CONTAINER", tags=["container", "norestore"])
        entry.value = "ghcr.io/tomcarman/skystats:0.1.13"
        data._env.add(entry)

        # Apply overrides (this should set it to myreg/skystats:v1)
        data._apply_image_overrides()

        # BUT sabotage: write the wrong value to config.json
        write_values_to_config_json(
            {"SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13"},
            reason="sabotaged config",
        )
        # .env also wrong
        write_values_to_env_file(
            {"SKYSTATS_CONTAINER": "ghcr.io/tomcarman/skystats:0.1.13"}
        )

        verified = vero.verify_image_overrides(strict=True)
        assert verified is False, "Mismatch must fail verification"

    def test_no_overrides_still_reaches_docker_update(self, adsb_test_env):
        """No override file at all must still allow reaching docker-update."""
        result = self._simulate_update_flow(
            adsb_test_env,
            "# no overrides, just a comment\n",
        )
        assert result["reached_docker_update"] is True, (
            "No overrides should allow reaching docker-update"
        )

    def test_empty_value_prevents_docker_update(self, adsb_test_env):
        """Empty override value prevents reaching docker-update."""
        result = self._simulate_update_flow(
            adsb_test_env,
            "SKYSTATS_CONTAINER=\n",
        )
        assert result["reached_docker_update"] is False, (
            "Empty value must abort before docker-update"
        )

    def test_unknown_key_prevents_docker_update(self, adsb_test_env):
        """Unknown override key prevents reaching docker-update in strict mode."""
        result = self._simulate_update_flow(
            adsb_test_env,
            "NONEXISTENT_CONTAINER=some/image:tag\n",
        )
        assert result["reached_docker_update"] is False, (
            "Unknown key must abort before docker-update"
        )

    def test_full_update_boundary_valid(self, adsb_test_env):
        """
        End-to-end: vendor SKYSTATS_CONTAINER replaced by override,
        both config.json and .env match -> docker-update reached.
        """
        result = self._simulate_update_flow(
            adsb_test_env,
            "SKYSTATS_CONTAINER=myreg/skystats:custom-v1\n",
        )
        assert result["reached_docker_update"] is True

        # Additionally confirm the override DID flow into config.json/.env
        from utils.config import read_values_from_config_json, read_values_from_env_file
        config = read_values_from_config_json(no_cache=True)
        env = read_values_from_env_file()
        assert config.get("SKYSTATS_CONTAINER") == "myreg/skystats:custom-v1"
        assert env.get("SKYSTATS_CONTAINER") == "myreg/skystats:custom-v1"
