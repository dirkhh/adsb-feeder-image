"""Page Object for Basic Setup page."""

import logging
import re
from html import unescape

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..base_page import BasePage
from ..config import Timeouts
from ..exceptions import ValidationError

logger = logging.getLogger(__name__)


class SystemMgmgtPage(BasePage):
    """Page object for the System Management page."""

    # Locators
    SYSTEMMGMT_PAGE_TITLE_TEXT = "System Management"
    LOGIN_PAGE_TITLE_TEXT = "automated test site: Login"
    USERNAME = (By.ID, "web_auth_username")
    SHOW_PASSWORD = (By.CSS_SELECTOR, '[data-test="show_passwd"]')
    PASSWORD = (By.CSS_SELECTOR, '[data-test="passwd"]')
    AUTH_ENABLE = (By.ID, "web_auth_enable")
    LOGIN_USERNAME = (By.ID, "username")
    LOGIN_PASSWORD = (By.ID, "password")
    LOGIN_BUTTON = (By.CSS_SELECTOR, '[data-test="login_button"]')

    def navigate(self) -> None:
        self.navigate_to("/systemmgmt")

    def verify_systemmgmt_loaded(self) -> bool:
        return self.verify_page_loaded(self.SYSTEMMGMT_PAGE_TITLE_TEXT)

    def verify_login_loaded(self) -> bool:
        return self.verify_page_loaded(self.LOGIN_PAGE_TITLE_TEXT)

    def setup_login(self):
        self.click_element(self.USERNAME)
        self.enter_text(self.USERNAME, "test")
        self.click_element(self.SHOW_PASSWORD)
        # Wait for the password element to have non-empty text
        password_element = WebDriverWait(self.driver, 5).until(lambda driver: driver.find_element(*self.PASSWORD))
        WebDriverWait(self.driver, 5).until(lambda _: password_element.text.strip() != "")
        password = str(password_element.text.strip())
        # Turn on authentication
        self.click_element(self.AUTH_ENABLE)

        return password

    def try_login(self, usename: str, password: str):
        self.click_element(self.LOGIN_USERNAME)
        self.enter_text(self.LOGIN_USERNAME, usename)
        self.click_element(self.LOGIN_PASSWORD)
        self.enter_text(self.LOGIN_PASSWORD, password)
        self.click_element(self.LOGIN_BUTTON)
