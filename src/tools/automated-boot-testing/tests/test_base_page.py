"""Tests for BasePage."""

from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium_framework.base_page import BasePage
from selenium_framework.exceptions import ElementNotFoundError


@pytest.fixture
def mock_driver():
    """Create mock WebDriver."""
    driver = MagicMock()
    driver.current_url = "http://test.com/page"
    driver.title = "Test Page"
    return driver


@pytest.fixture
def base_page(mock_driver):
    """Create BasePage instance."""
    return BasePage(mock_driver, "http://test.com")


def test_navigate_to(base_page, mock_driver):
    """Test navigate_to method."""
    base_page.navigate_to("/setup")
    mock_driver.get.assert_called_once_with("http://test.com/setup")


def test_get_current_url(base_page):
    """Test get_current_url method."""
    assert base_page.get_current_url() == "http://test.com/page"


def test_get_current_title(base_page):
    """Test get_current_title method."""
    assert base_page.get_current_title() == "Test Page"


@patch("selenium_framework.base_page.WebDriverWait")
def test_find_element_success(mock_wait, base_page, mock_driver):
    """Test finding element successfully."""
    mock_element = MagicMock()
    mock_wait.return_value.until.return_value = mock_element

    locator = (By.ID, "test_id")
    element = base_page.find_element(locator)

    assert element == mock_element


@patch("selenium_framework.base_page.WebDriverWait")
def test_find_element_timeout(mock_wait, base_page):
    """Test finding element timeout."""
    mock_wait.return_value.until.side_effect = TimeoutException()

    locator = (By.ID, "test_id")
    with pytest.raises(ElementNotFoundError, match="Element not found"):
        base_page.find_element(locator)


def test_find_elements(base_page, mock_driver):
    """Test finding multiple elements."""
    mock_elements = [MagicMock(), MagicMock()]
    mock_driver.find_elements.return_value = mock_elements

    locator = (By.CLASS_NAME, "test_class")
    elements = base_page.find_elements(locator)

    assert elements == mock_elements
    mock_driver.find_elements.assert_called_once_with(By.CLASS_NAME, "test_class")


@patch("selenium_framework.base_page.WebDriverWait")
def test_click_element_success(mock_wait, base_page):
    """Test clicking element successfully."""
    mock_element = MagicMock()
    mock_wait.return_value.until.return_value = mock_element

    locator = (By.ID, "button_id")
    base_page.click_element(locator)

    mock_element.click.assert_called_once()


@patch("selenium_framework.base_page.WebDriverWait")
def test_click_element_with_js_fallback(mock_wait, base_page, mock_driver):
    """Test clicking element with JavaScript fallback."""
    mock_element = MagicMock()
    mock_element.click.side_effect = Exception("Click failed")
    mock_wait.return_value.until.return_value = mock_element

    locator = (By.ID, "button_id")
    base_page.click_element(locator)

    mock_driver.execute_script.assert_called_once()


@patch("selenium_framework.base_page.WebDriverWait")
def test_enter_text(mock_wait, base_page):
    """Test entering text into element."""
    mock_element = MagicMock()
    mock_wait.return_value.until.return_value = mock_element

    locator = (By.ID, "input_id")
    base_page.enter_text(locator, "test text")

    mock_element.clear.assert_called_once()
    mock_element.send_keys.assert_called_once_with("test text")


@patch("selenium_framework.base_page.WebDriverWait")
def test_enter_text_no_clear(mock_wait, base_page):
    """Test entering text without clearing."""
    mock_element = MagicMock()
    mock_wait.return_value.until.return_value = mock_element

    locator = (By.ID, "input_id")
    base_page.enter_text(locator, "test text", clear_first=False)

    mock_element.clear.assert_not_called()
    mock_element.send_keys.assert_called_once_with("test text")
