"""
Centralized path configuration for adsb-setup application.

This module provides configurable paths that can be overridden via environment variables
for testing and different deployment scenarios.

All paths are computed lazily from the base directory, eliminating the need for
manual reinitialization when the base directory changes.
"""

import os
from pathlib import Path


class PathConfig:
    """
    Lazy-loading path configuration.

    All paths are computed on-demand from the base directory, which can be
    changed at runtime. This eliminates the need for manual reinitialization
    of dozens of path constants.
    """

    def __init__(self):
        self._base_dir = None
        self._skystats_db_data_path = None

    @property
    def ADSB_BASE_DIR(self) -> Path:
        """Base directory - configurable via ADSB_BASE_DIR environment variable."""
        if self._base_dir is None:
            self._base_dir = Path(os.environ.get("ADSB_BASE_DIR", "/opt/adsb"))
        return self._base_dir

    @ADSB_BASE_DIR.setter
    def ADSB_BASE_DIR(self, value: Path):
        """Set the base directory (used by set_adsb_base_dir)."""
        self._base_dir = Path(value)
        # Clear cached skystats path when base dir changes
        self._skystats_db_data_path = None

    # Main directories
    @property
    def ADSB_CONFIG_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "config"

    @property
    def ADSB_DATA_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "data"

    @property
    def ADSB_SCRIPTS_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "scripts"

    @property
    def ADSB_LOGS_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "logs"

    @property
    def ADSB_EXTRAS_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "extras"

    @property
    def ADSB_RB_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "rb"

    # Configuration files
    @property
    def VERBOSE_FILE(self) -> Path:
        return self.ADSB_CONFIG_DIR / "verbose"

    @property
    def ENV_FILE(self) -> Path:
        return self.ADSB_CONFIG_DIR / ".env"

    @property
    def USER_ENV_FILE(self) -> Path:
        return self.ADSB_CONFIG_DIR / ".env.user"

    @property
    def CONFIG_JSON_FILE(self) -> Path:
        return self.ADSB_CONFIG_DIR / "config.json"

    # System files
    @property
    def MACHINE_ID_FILE(self) -> Path:
        """System file, not configurable."""
        return Path("/etc/machine-id")

    @property
    def SECURE_IMAGE_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "adsb.im.secure_image"

    @property
    def FEEDER_IMAGE_NAME_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "feeder-image.name"

    @property
    def PREVIOUS_VERSION_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "adsb.im.previous-version"

    @property
    def HOTSPOT_DISABLED_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "adsb.im.hotspot_disabled"

    @property
    def PASSWD_AND_KEYS_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "adsb.im.passwd.and.keys"

    # Version files
    @property
    def VERSION_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "adsb.im.version"

    @property
    def OS_FEEDER_IMAGE_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "os.adsb.feeder.image"

    @property
    def DOCKER_IMAGE_VERSIONS_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "docker.image.versions"

    # Application-specific paths
    @property
    def ULTRAFEEDER_CONFIG_DIR(self) -> Path:
        return self.ADSB_CONFIG_DIR / "ultrafeeder"

    @property
    def NANOFEEDER_CONFIG_DIR(self) -> Path:
        return self.ADSB_CONFIG_DIR / "nanofeeder"

    @property
    def RESTORE_DIR(self) -> Path:
        return self.ADSB_CONFIG_DIR / "restore"

    @property
    def ACARSHUB_DATA_DIR(self) -> Path:
        return self.ADSB_CONFIG_DIR / "acarshub_data"

    # Script files
    @property
    def MDNS_ALIAS_SETUP_SCRIPT(self) -> Path:
        return self.ADSB_SCRIPTS_DIR / "mdns-alias-setup.sh"

    @property
    def PUSH_MULTIOUTLINE_SCRIPT(self) -> Path:
        return self.ADSB_BASE_DIR / "push_multioutline.sh"

    @property
    def JOURNAL_SET_VOLATILE_SCRIPT(self) -> Path:
        return self.ADSB_SCRIPTS_DIR / "journal-set-volatile.sh"

    @property
    def JOURNAL_SET_PERSIST_SCRIPT(self) -> Path:
        return self.ADSB_SCRIPTS_DIR / "journal-set-persist.sh"

    @property
    def LOG_SANITIZER_SCRIPT(self) -> Path:
        return self.ADSB_BASE_DIR / "log-sanitizer.sh"

    # Docker compose files
    @property
    def DOCKER_COMPOSE_ADSB_SCRIPT(self) -> Path:
        return self.ADSB_BASE_DIR / "docker-compose-adsb"

    @property
    def DOCKER_COMPOSE_START_SCRIPT(self) -> Path:
        return self.ADSB_BASE_DIR / "docker-compose-start"

    # Log files
    @property
    def NETDOG_LOG_FILE(self) -> Path:
        return self.ADSB_LOGS_DIR / "netdog.log"

    # Template files
    @property
    def DOZZLE_TEMPLATE_FILE(self) -> Path:
        return self.ADSB_CONFIG_DIR / "dozzle_template.yml"

    @property
    def DOZZLE_CONFIG_FILE(self) -> Path:
        return self.ADSB_CONFIG_DIR / "dozzle.yml"

    # HFDL Observer paths
    @property
    def HFDLOBSERVER_COMPOSE_DIR(self) -> Path:
        return self.ADSB_BASE_DIR / "hfdlobserver" / "compose"

    @property
    def HFDLOBSERVER_SETTINGS_TEMPLATE(self) -> Path:
        return self.HFDLOBSERVER_COMPOSE_DIR / "settings.yaml.sample"

    @property
    def HFDLOBSERVER_SETTINGS_FILE(self) -> Path:
        return self.HFDLOBSERVER_COMPOSE_DIR / "settings.yaml"

    @property
    def HFDLOBSERVER_SETTINGS_BACKUP(self) -> Path:
        return self.HFDLOBSERVER_COMPOSE_DIR / "settings.yaml.bak"

    # Radiosonde paths
    @property
    def RADIOSONDE_STATION_TEMPLATE(self) -> Path:
        return self.ADSB_BASE_DIR / "radiosonde" / "station.cfg.template"

    @property
    def RADIOSONDE_STATION_CONFIG(self) -> Path:
        return self.ADSB_BASE_DIR / "radiosonde" / "station.cfg"

    @property
    def RADIOSONDE_STATION_BACKUP(self) -> Path:
        return self.ADSB_BASE_DIR / "radiosonde" / "station.cfg.bak"

    # Temperature monitoring
    @property
    def ADSB_TEMPERATURE_DEFAULT(self) -> Path:
        return self.ADSB_EXTRAS_DIR / "adsb-temperature.default"

    # State files
    @property
    def COMPOSE_UP_FAILED_STATE(self) -> Path:
        return self.ADSB_BASE_DIR / "state" / "compose_up_failed"

    # Data files
    @property
    def PLANES_SEEN_PER_DAY_FILE(self) -> Path:
        return self.ADSB_BASE_DIR / "adsb_planes_seen_per_day.json.gz"

    # Fake files for testing/simulation
    @property
    def FAKE_CPUINFO_DIR(self) -> Path:
        return self.ADSB_RB_DIR

    @property
    def FAKE_THERMAL_ZONE_DIR(self) -> Path:
        return self.ADSB_RB_DIR / "thermal_zone0"

    @property
    def FAKE_THERMAL_TEMP_FILE(self) -> Path:
        return self.FAKE_THERMAL_ZONE_DIR / "temp"

    # Skystats
    @property
    def SKYSTATS_DB_DATA_PATH(self) -> Path:
        """Skystats DB path - configurable via SKYSTATS_DB_DATA_PATH environment variable."""
        if self._skystats_db_data_path is None:
            self._skystats_db_data_path = Path(os.environ.get("SKYSTATS_DB_DATA_PATH", str(self.ADSB_BASE_DIR / "skystats-db")))
        return self._skystats_db_data_path


# Singleton instance
_config = PathConfig()


# Public API functions
def get_adsb_base_dir() -> Path:
    """Get the current ADS-B base directory."""
    return _config.ADSB_BASE_DIR


def get_config_dir() -> Path:
    """Get the current configuration directory."""
    return _config.ADSB_CONFIG_DIR


def set_adsb_base_dir(base_dir: str) -> None:
    """
    Set the ADS-B base directory.

    All derived paths are automatically recalculated due to lazy evaluation.
    No manual reinitialization needed.
    """
    _config.ADSB_BASE_DIR = Path(base_dir)


# Backward compatibility: expose paths as module-level attributes
# This allows existing code to continue using: from .paths import VERBOSE_FILE
def __getattr__(name):
    """Delegate attribute access to the singleton PathConfig instance."""
    if hasattr(_config, name):
        return getattr(_config, name)
    raise AttributeError(f"module 'paths' has no attribute '{name}'")
