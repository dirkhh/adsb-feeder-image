"""Page Object for Basic Setup page."""

import logging
import re
from html import unescape

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
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
    SHOW_AUTH_PASSWORD = (By.CSS_SELECTOR, '[data-test="show_auth_passwd"]')
    AUTH_PASSWORD = (By.CSS_SELECTOR, '[data-test="auth_passwd"]')
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

    def setup_login(self, username: str):
        logger.info("Enter user name")
        self.click_element(self.USERNAME)
        self.enter_text(self.USERNAME, username)
        logger.info("Reveal and copy password")
        self.click_element(self.SHOW_AUTH_PASSWORD)
        # Wait for the password element to have non-empty text
        password_element = WebDriverWait(self.driver, 5).until(lambda driver: driver.find_element(*self.AUTH_PASSWORD))
        WebDriverWait(self.driver, 5).until(lambda _: password_element.text.strip() != "")
        password = str(password_element.text.strip())
        # Turn on authentication
        logger.info("Wait for authentication button to be clickable")
        WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(self.AUTH_ENABLE))
        logger.info("Enable authentication")
        self.click_element(self.AUTH_ENABLE)

        return password

    def try_login(self, usename: str, password: str):
        logger.info("Enter username and password")
        self.click_element(self.LOGIN_USERNAME)
        self.enter_text(self.LOGIN_USERNAME, usename)
        self.click_element(self.LOGIN_PASSWORD)
        self.enter_text(self.LOGIN_PASSWORD, password)
        logger.info("Click login button")
        self.click_element(self.LOGIN_BUTTON)
