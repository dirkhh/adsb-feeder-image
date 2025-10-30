"""Tests for configuration classes."""

from selenium_framework.config import SeleniumConfig, Timeouts


def test_test_config_defaults():
    """Test SeleniumConfig with default values."""
    config = SeleniumConfig(rpi_ip="192.168.1.100")

    assert config.rpi_ip == "192.168.1.100"
    assert config.browser == "chrome"
    assert config.headless is True
    assert config.timeout == 90
    assert config.site_name == "automated test site"
    assert config.latitude == 45.48
    assert config.longitude == -122.66
    assert config.altitude == 30


def test_test_config_custom_values():
    """Test SeleniumConfig with custom values."""
    config = SeleniumConfig(
        rpi_ip="10.0.0.50",
        browser="firefox",
        headless=False,
        timeout=120,
        site_name="test site 2",
        latitude=37.77,
        longitude=-122.42,
        altitude=15,
    )

    assert config.rpi_ip == "10.0.0.50"
    assert config.browser == "firefox"
    assert config.headless is False
    assert config.timeout == 120
    assert config.site_name == "test site 2"


def test_test_config_base_url():
    """Test base_url property."""
    config = SeleniumConfig(rpi_ip="192.168.1.100")
    assert config.base_url == "http://192.168.1.100"


def test_timeouts_constants():
    """Test Timeouts class has expected constants."""
    assert Timeouts.PAGE_LOAD == 30
    assert Timeouts.SHORT_WAIT == 5
    assert Timeouts.MEDIUM_WAIT == 30
    assert Timeouts.LONG_WAIT == 600
    assert Timeouts.JS_SETTLE == 1
    assert Timeouts.API_DATA_LOAD == 30
