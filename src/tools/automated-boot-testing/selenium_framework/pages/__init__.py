"""Page objects for the selenium test framework."""

from .basic_setup_page import BasicSetupPage
from .feeder_homepage import FeederHomepage
from .sdr_setup_page import SDRInfo, SDRSetupPage
from .waiting_page import WaitingPage

__all__ = ["BasicSetupPage", "SDRSetupPage", "FeederHomepage", "WaitingPage", "SDRInfo"]
