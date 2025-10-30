"""Custom exceptions for selenium test framework."""


class SeleniumTestError(Exception):
    """Base exception for all test failures."""

    pass


class ElementNotFoundError(SeleniumTestError):
    """Element was not found on the page."""

    pass


class ValidationError(SeleniumTestError):
    """Expected condition or validation failed."""

    pass


class PageTransitionError(SeleniumTestError):
    """Page failed to transition to expected state."""

    pass


class BrowserSetupError(SeleniumTestError):
    """Browser initialization failed."""

    pass
