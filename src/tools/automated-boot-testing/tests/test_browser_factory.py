"""Tests for BrowserFactory."""

from unittest.mock import MagicMock, patch

import pytest
from selenium_framework.browser_factory import BrowserFactory
from selenium_framework.exceptions import BrowserSetupError


@patch("selenium_framework.browser_factory.webdriver.Chrome")
def test_create_chrome_driver(mock_chrome):
    """Test creating Chrome driver with Selenium Manager."""
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    driver = BrowserFactory.create_driver(browser_type="chrome", headless=True)

    assert driver == mock_driver
    mock_chrome.assert_called_once()
    mock_driver.set_page_load_timeout.assert_called_once()


@patch("selenium_framework.browser_factory.webdriver.Firefox")
def test_create_firefox_driver(mock_firefox):
    """Test creating Firefox driver with Selenium Manager."""
    mock_driver = MagicMock()
    mock_firefox.return_value = mock_driver

    driver = BrowserFactory.create_driver(browser_type="firefox", headless=True)

    assert driver == mock_driver
    mock_firefox.assert_called_once()
    mock_driver.set_page_load_timeout.assert_called_once()


def test_create_driver_invalid_browser():
    """Test creating driver with invalid browser type."""
    with pytest.raises(BrowserSetupError, match="Unsupported browser type"):
        BrowserFactory.create_driver(browser_type="invalid")  # type: ignore[arg-type]


@patch("selenium_framework.browser_factory.webdriver.Chrome")
def test_create_driver_failure(mock_chrome):
    """Test browser creation failure with Selenium Manager."""
    mock_chrome.side_effect = Exception("Browser failed")

    with pytest.raises(BrowserSetupError, match="Failed to create chrome browser"):
        BrowserFactory.create_driver(browser_type="chrome")
