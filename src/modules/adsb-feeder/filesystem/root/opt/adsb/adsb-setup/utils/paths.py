"""
Centralized path configuration for adsb-setup application.

This module provides configurable paths that can be overridden via environment variables
for testing and different deployment scenarios.
"""

import os
from pathlib import Path

# Base directory - configurable via ADSB_BASE_DIR environment variable
ADSB_BASE_DIR = Path(os.environ.get("ADSB_BASE_DIR", "/opt/adsb"))

# Main directories
ADSB_CONFIG_DIR = ADSB_BASE_DIR / "config"
ADSB_DATA_DIR = ADSB_BASE_DIR / "data"
ADSB_SCRIPTS_DIR = ADSB_BASE_DIR / "scripts"
ADSB_LOGS_DIR = ADSB_BASE_DIR / "logs"
ADSB_EXTRAS_DIR = ADSB_BASE_DIR / "extras"
ADSB_RB_DIR = ADSB_BASE_DIR / "rb"

# Configuration files
VERBOSE_FILE = ADSB_CONFIG_DIR / "verbose"
ENV_FILE = ADSB_CONFIG_DIR / ".env"
USER_ENV_FILE = ADSB_CONFIG_DIR / ".env.user"
CONFIG_JSON_FILE = ADSB_CONFIG_DIR / "config.json"

# System files
MACHINE_ID_FILE = Path("/etc/machine-id")  # System file, not configurable
SECURE_IMAGE_FILE = ADSB_BASE_DIR / "adsb.im.secure_image"
FEEDER_IMAGE_NAME_FILE = ADSB_BASE_DIR / "feeder-image.name"
PREVIOUS_VERSION_FILE = ADSB_BASE_DIR / "adsb.im.previous-version"
HOTSPOT_DISABLED_FILE = ADSB_BASE_DIR / "adsb.im.hotspot_disabled"
PASSWD_AND_KEYS_FILE = ADSB_BASE_DIR / "adsb.im.passwd.and.keys"

# Version files
VERSION_FILE = ADSB_BASE_DIR / "adsb.im.version"
OS_FEEDER_IMAGE_FILE = ADSB_BASE_DIR / "os.adsb.feeder.image"
DOCKER_IMAGE_VERSIONS_FILE = ADSB_BASE_DIR / "docker.image.versions"

# Application-specific paths
ULTRAFEEDER_CONFIG_DIR = ADSB_CONFIG_DIR / "ultrafeeder"
NANOFEEDER_CONFIG_DIR = ADSB_CONFIG_DIR / "nanofeeder"
RESTORE_DIR = ADSB_CONFIG_DIR / "restore"
ACARSHUB_DATA_DIR = ADSB_CONFIG_DIR / "acarshub_data"

# Script files
MDNS_ALIAS_SETUP_SCRIPT = ADSB_SCRIPTS_DIR / "mdns-alias-setup.sh"
PUSH_MULTIOUTLINE_SCRIPT = ADSB_BASE_DIR / "push_multioutline.sh"
JOURNAL_SET_VOLATILE_SCRIPT = ADSB_SCRIPTS_DIR / "journal-set-volatile.sh"
JOURNAL_SET_PERSIST_SCRIPT = ADSB_SCRIPTS_DIR / "journal-set-persist.sh"
LOG_SANITIZER_SCRIPT = ADSB_BASE_DIR / "log-sanitizer.sh"

# Docker compose files
DOCKER_COMPOSE_ADSB_SCRIPT = ADSB_BASE_DIR / "docker-compose-adsb"
DOCKER_COMPOSE_START_SCRIPT = ADSB_BASE_DIR / "docker-compose-start"

# Log files
NETDOG_LOG_FILE = ADSB_LOGS_DIR / "netdog.log"

# Template files
DOZZLE_TEMPLATE_FILE = ADSB_CONFIG_DIR / "dozzle_template.yml"
DOZZLE_CONFIG_FILE = ADSB_CONFIG_DIR / "dozzle.yml"

# HFDL Observer paths
HFDLOBSERVER_COMPOSE_DIR = ADSB_BASE_DIR / "hfdlobserver" / "compose"
HFDLOBSERVER_SETTINGS_TEMPLATE = HFDLOBSERVER_COMPOSE_DIR / "settings.yaml.sample"
HFDLOBSERVER_SETTINGS_FILE = HFDLOBSERVER_COMPOSE_DIR / "settings.yaml"
HFDLOBSERVER_SETTINGS_BACKUP = HFDLOBSERVER_COMPOSE_DIR / "settings.yaml.bak"

# Radiosonde paths
RADIOSONDE_STATION_TEMPLATE = ADSB_BASE_DIR / "radiosonde" / "station.cfg.template"
RADIOSONDE_STATION_CONFIG = ADSB_BASE_DIR / "radiosonde" / "station.cfg"
RADIOSONDE_STATION_BACKUP = ADSB_BASE_DIR / "radiosonde" / "station.cfg.bak"

# Temperature monitoring
ADSB_TEMPERATURE_DEFAULT = ADSB_EXTRAS_DIR / "adsb-temperature.default"

# State files
COMPOSE_UP_FAILED_STATE = ADSB_BASE_DIR / "state" / "compose_up_failed"

# Data files
PLANES_SEEN_PER_DAY_FILE = ADSB_BASE_DIR / "adsb_planes_seen_per_day.json.gz"

# Fake files for testing/simulation
FAKE_CPUINFO_DIR = ADSB_RB_DIR
FAKE_THERMAL_ZONE_DIR = ADSB_RB_DIR / "thermal_zone0"
FAKE_THERMAL_TEMP_FILE = FAKE_THERMAL_ZONE_DIR / "temp"

# Skystats
SKYSTATS_DB_DATA_PATH = Path(os.environ.get("SKYSTATS_DB_DATA_PATH", str(ADSB_BASE_DIR / "skystats-db")))


def get_adsb_base_dir() -> Path:
    """Get the current ADS-B base directory."""
    return ADSB_BASE_DIR


def get_config_dir() -> Path:
    """Get the current configuration directory."""
    return ADSB_CONFIG_DIR


def set_adsb_base_dir(base_dir: str) -> None:
    """
    Set the ADS-B base directory.

    Note: This should be called at application startup before any other modules
    import the path constants.
    """
    global ADSB_BASE_DIR
    ADSB_BASE_DIR = Path(base_dir)
    # Re-initialize all derived paths
    _reinitialize_paths()


def _reinitialize_paths():
    """Re-initialize all path constants after base directory change."""
    global ADSB_CONFIG_DIR, ADSB_DATA_DIR, ADSB_SCRIPTS_DIR, ADSB_LOGS_DIR
    global ADSB_EXTRAS_DIR, ADSB_RB_DIR, VERBOSE_FILE, ENV_FILE, USER_ENV_FILE
    global CONFIG_JSON_FILE, SECURE_IMAGE_FILE, FEEDER_IMAGE_NAME_FILE
    global PREVIOUS_VERSION_FILE, HOTSPOT_DISABLED_FILE, PASSWD_AND_KEYS_FILE
    global VERSION_FILE, OS_FEEDER_IMAGE_FILE, DOCKER_IMAGE_VERSIONS_FILE, ULTRAFEEDER_CONFIG_DIR
    global NANOFEEDER_CONFIG_DIR, RESTORE_DIR, ACARSHUB_DATA_DIR
    global MDNS_ALIAS_SETUP_SCRIPT, PUSH_MULTIOUTLINE_SCRIPT
    global JOURNAL_SET_VOLATILE_SCRIPT, JOURNAL_SET_PERSIST_SCRIPT
    global LOG_SANITIZER_SCRIPT, DOCKER_COMPOSE_ADSB_SCRIPT
    global DOCKER_COMPOSE_START_SCRIPT, NETDOG_LOG_FILE
    global DOZZLE_TEMPLATE_FILE, DOZZLE_CONFIG_FILE
    global HFDLOBSERVER_COMPOSE_DIR, HFDLOBSERVER_SETTINGS_TEMPLATE
    global HFDLOBSERVER_SETTINGS_FILE, HFDLOBSERVER_SETTINGS_BACKUP
    global RADIOSONDE_STATION_TEMPLATE, RADIOSONDE_STATION_CONFIG
    global RADIOSONDE_STATION_BACKUP, ADSB_TEMPERATURE_DEFAULT
    global COMPOSE_UP_FAILED_STATE, PLANES_SEEN_PER_DAY_FILE
    global FAKE_CPUINFO_DIR, FAKE_THERMAL_ZONE_DIR, FAKE_THERMAL_TEMP_FILE

    ADSB_CONFIG_DIR = ADSB_BASE_DIR / "config"
    ADSB_DATA_DIR = ADSB_BASE_DIR / "data"
    ADSB_SCRIPTS_DIR = ADSB_BASE_DIR / "scripts"
    ADSB_LOGS_DIR = ADSB_BASE_DIR / "logs"
    ADSB_EXTRAS_DIR = ADSB_BASE_DIR / "extras"
    ADSB_RB_DIR = ADSB_BASE_DIR / "rb"

    VERBOSE_FILE = ADSB_CONFIG_DIR / "verbose"
    ENV_FILE = ADSB_CONFIG_DIR / ".env"
    USER_ENV_FILE = ADSB_CONFIG_DIR / ".env.user"
    CONFIG_JSON_FILE = ADSB_CONFIG_DIR / "config.json"

    SECURE_IMAGE_FILE = ADSB_BASE_DIR / "adsb.im.secure_image"
    FEEDER_IMAGE_NAME_FILE = ADSB_BASE_DIR / "feeder-image.name"
    PREVIOUS_VERSION_FILE = ADSB_BASE_DIR / "adsb.im.previous-version"
    HOTSPOT_DISABLED_FILE = ADSB_BASE_DIR / "adsb.im.hotspot_disabled"
    PASSWD_AND_KEYS_FILE = ADSB_BASE_DIR / "adsb.im.passwd.and.keys"

    VERSION_FILE = ADSB_BASE_DIR / "adsb.im.version"
    OS_FEEDER_IMAGE_FILE = ADSB_BASE_DIR / "os.adsb.feeder.image"
    DOCKER_IMAGE_VERSIONS_FILE = ADSB_BASE_DIR / "docker.image.versions"

    ULTRAFEEDER_CONFIG_DIR = ADSB_CONFIG_DIR / "ultrafeeder"
    NANOFEEDER_CONFIG_DIR = ADSB_CONFIG_DIR / "nanofeeder"
    RESTORE_DIR = ADSB_CONFIG_DIR / "restore"
    ACARSHUB_DATA_DIR = ADSB_CONFIG_DIR / "acarshub_data"

    MDNS_ALIAS_SETUP_SCRIPT = ADSB_SCRIPTS_DIR / "mdns-alias-setup.sh"
    PUSH_MULTIOUTLINE_SCRIPT = ADSB_BASE_DIR / "push_multioutline.sh"
    JOURNAL_SET_VOLATILE_SCRIPT = ADSB_SCRIPTS_DIR / "journal-set-volatile.sh"
    JOURNAL_SET_PERSIST_SCRIPT = ADSB_SCRIPTS_DIR / "journal-set-persist.sh"
    LOG_SANITIZER_SCRIPT = ADSB_BASE_DIR / "log-sanitizer.sh"

    DOCKER_COMPOSE_ADSB_SCRIPT = ADSB_BASE_DIR / "docker-compose-adsb"
    DOCKER_COMPOSE_START_SCRIPT = ADSB_BASE_DIR / "docker-compose-start"

    NETDOG_LOG_FILE = ADSB_LOGS_DIR / "netdog.log"

    DOZZLE_TEMPLATE_FILE = ADSB_CONFIG_DIR / "dozzle_template.yml"
    DOZZLE_CONFIG_FILE = ADSB_CONFIG_DIR / "dozzle.yml"

    HFDLOBSERVER_COMPOSE_DIR = ADSB_BASE_DIR / "hfdlobserver" / "compose"
    HFDLOBSERVER_SETTINGS_TEMPLATE = HFDLOBSERVER_COMPOSE_DIR / "settings.yaml.sample"
    HFDLOBSERVER_SETTINGS_FILE = HFDLOBSERVER_COMPOSE_DIR / "settings.yaml"
    HFDLOBSERVER_SETTINGS_BACKUP = HFDLOBSERVER_COMPOSE_DIR / "settings.yaml.bak"

    RADIOSONDE_STATION_TEMPLATE = ADSB_BASE_DIR / "radiosonde" / "station.cfg.template"
    RADIOSONDE_STATION_CONFIG = ADSB_BASE_DIR / "radiosonde" / "station.cfg"
    RADIOSONDE_STATION_BACKUP = ADSB_BASE_DIR / "radiosonde" / "station.cfg.bak"

    ADSB_TEMPERATURE_DEFAULT = ADSB_EXTRAS_DIR / "adsb-temperature.default"

    COMPOSE_UP_FAILED_STATE = ADSB_BASE_DIR / "state" / "compose_up_failed"

    PLANES_SEEN_PER_DAY_FILE = ADSB_BASE_DIR / "adsb_planes_seen_per_day.json.gz"

    FAKE_CPUINFO_DIR = ADSB_RB_DIR
    FAKE_THERMAL_ZONE_DIR = ADSB_RB_DIR / "thermal_zone0"
    FAKE_THERMAL_TEMP_FILE = FAKE_THERMAL_ZONE_DIR / "temp"
