"""
Tests for the two mutually exclusive ShipXplorer feed methods
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from app import AdsbIm

ADSB_ROOT = Path(__file__).parent.parent.parent / "src" / "modules" / "adsb-feeder" / "filesystem" / "root" / "opt" / "adsb"

SX_TAGS = [
    "ais_feed_shipxplorer",
    "ais_shipxplorer_method",
    "ais_shipxplorer_sharing_key",
    "ais_shipxplorer_serial_number",
    "ais_shipxplorer_udp_port",
]


class FakeEnv:
    """Minimal stand in for utils.environment.Env holding a single element list"""

    def __init__(self, value=""):
        self._value = [value]

    def list_get(self, idx):
        return self._value[idx]

    def list_set(self, idx, value):
        self._value[idx] = value


@pytest.fixture
def sx_app():
    """An AdsbIm whose ShipXplorer env lookups are backed by a plain dict"""
    with patch("app.Data") as mock_data, patch("app.System"), patch("app.RouteManager"):
        mock_data_instance = MagicMock()
        mock_data_instance.env_by_tags.return_value = MagicMock(valuestr="1.0.0")
        mock_data_instance.version_file = "/tmp/test_version"
        mock_data_instance.proxy_routes = []
        mock_data.return_value = mock_data_instance
        adsb_im = AdsbIm()

    envs = {tag: FakeEnv("") for tag in SX_TAGS}
    envs["ais_feed_shipxplorer"] = FakeEnv(True)
    adsb_im._d.env_by_tags = lambda tags: envs[tags]
    # the shipfeeder itself is on unless a test says otherwise
    adsb_im._d.is_enabled = lambda tags: True
    return adsb_im, envs


class TestShipXplorerMethod:
    """The method is remembered, and inferred for feeders that predate the choice"""

    def test_fresh_feeder_defaults_to_station(self, sx_app):
        adsb_im, _ = sx_app
        assert adsb_im.shipxplorer_method() == "station"

    def test_existing_udp_port_is_kept_as_udp(self, sx_app):
        # a feeder configured before the choice existed only has a UDP port
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_udp_port"].list_set(0, "12345")

        assert adsb_im.shipxplorer_method() == "udp"
        adsb_im.update_shipxplorer_config()
        assert envs["ais_shipxplorer_udp_port"].list_get(0) == "12345"

    @pytest.mark.parametrize("method", ["udp", "station"])
    def test_explicit_method_wins_over_inference(self, sx_app, method):
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, method)
        envs["ais_shipxplorer_udp_port"].list_set(0, "12345")

        assert adsb_im.shipxplorer_method() == method

    def test_method_is_persisted(self, sx_app):
        adsb_im, envs = sx_app
        adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_method"].list_get(0) == "station"


class TestShipXplorerMutualExclusion:
    """Only ever pass one of the two methods to the container"""

    def test_station_clears_the_udp_port(self, sx_app):
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")
        envs["ais_shipxplorer_serial_number"].list_set(0, "SXTRPI001234")
        envs["ais_shipxplorer_udp_port"].list_set(0, "12345")

        adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_sharing_key"].list_get(0) == "a-sharing-key"
        assert envs["ais_shipxplorer_serial_number"].list_get(0) == "SXTRPI001234"
        assert envs["ais_shipxplorer_udp_port"].list_get(0) == ""

    def test_udp_clears_key_and_serial(self, sx_app):
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, "udp")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")
        envs["ais_shipxplorer_serial_number"].list_set(0, "SXTRPI001234")
        envs["ais_shipxplorer_udp_port"].list_set(0, "12345")

        adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_sharing_key"].list_get(0) == ""
        assert envs["ais_shipxplorer_serial_number"].list_get(0) == ""
        assert envs["ais_shipxplorer_udp_port"].list_get(0) == "12345"

    def test_disabled_clears_everything(self, sx_app):
        adsb_im, envs = sx_app
        envs["ais_feed_shipxplorer"].list_set(0, False)
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")
        envs["ais_shipxplorer_serial_number"].list_set(0, "SXTRPI001234")
        envs["ais_shipxplorer_udp_port"].list_set(0, "12345")

        adsb_im.update_shipxplorer_config()

        for tag in ["ais_shipxplorer_sharing_key", "ais_shipxplorer_serial_number", "ais_shipxplorer_udp_port"]:
            assert envs[tag].list_get(0) == ""

    @patch("app.report_issue")
    def test_half_configured_station_is_reported(self, mock_report_issue, sx_app):
        # without both values sxfeeder does nothing, so the user needs to hear about it
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")

        adsb_im.update_shipxplorer_config()

        mock_report_issue.assert_called_once()

    @patch("app.report_issue")
    def test_fully_configured_station_is_not_reported(self, mock_report_issue, sx_app):
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")
        envs["ais_shipxplorer_serial_number"].list_set(0, "SXTRPI001234")

        adsb_im.update_shipxplorer_config()

        mock_report_issue.assert_not_called()

    @patch("app.report_issue")
    def test_half_configured_station_is_not_reported_without_a_shipfeeder(self, mock_report_issue, sx_app):
        adsb_im, envs = sx_app
        adsb_im._d.is_enabled = lambda tags: False
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")

        adsb_im.update_shipxplorer_config()

        mock_report_issue.assert_not_called()

    def test_the_two_methods_are_separated_even_without_a_shipfeeder(self, sx_app):
        # no SDR assigned yet, so the shipfeeder isn't running -- the settings still have to
        # be sorted out now, or both methods are live the moment it does start
        adsb_im, envs = sx_app
        adsb_im._d.is_enabled = lambda tags: False
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")
        envs["ais_shipxplorer_serial_number"].list_set(0, "SXTRPI001234")
        envs["ais_shipxplorer_udp_port"].list_set(0, "12345")

        adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_udp_port"].list_get(0) == ""


class TestShipXplorerContainerConfig:
    """The container needs both values to start sxfeeder at all"""

    def test_shipfeeder_yml_passes_key_and_serial(self):
        yml = (ADSB_ROOT / "shipfeeder.yml").read_text()

        assert "SHIPXPLORER_SHARING_KEY=${AIS_SHIPXPLORER_SHARING_KEY}" in yml
        assert "SHIPXPLORER_SERIAL_NUMBER=${AIS_SHIPXPLORER_SERIAL_NUMBER}" in yml

    def test_envs_are_defined(self, adsb_test_env):
        # import here, not at module level: other tests reload utils.data, which replaces the class
        import utils.data

        utils.data.Data.reset_for_testing()
        d = utils.data.Data()

        assert d.env_by_tags("ais_shipxplorer_sharing_key").name == "AIS_SHIPXPLORER_SHARING_KEY"
        assert d.env_by_tags("ais_shipxplorer_serial_number").name == "AIS_SHIPXPLORER_SERIAL_NUMBER"
        assert d.env_by_tags("ais_shipxplorer_method").name == "_ADSBIM_STATE_AIS_SHIPXPLORER_METHOD"


class TestShipXplorerWhitespace:
    """Values are normalized the same way the env file exports them"""

    def test_whitespace_only_serial_counts_as_missing(self, sx_app):
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "a-sharing-key")
        envs["ais_shipxplorer_serial_number"].list_set(0, "   ")

        with patch("app.report_issue") as mock_report_issue:
            adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_serial_number"].list_get(0) == ""
        mock_report_issue.assert_called_once()

    def test_whitespace_only_port_does_not_look_like_a_udp_feeder(self, sx_app):
        # an unset method is inferred from the port, which must not be fooled by blanks
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_udp_port"].list_set(0, "  ")

        adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_method"].list_get(0) == "station"

    def test_surrounding_whitespace_is_trimmed_off_the_credentials(self, sx_app):
        adsb_im, envs = sx_app
        envs["ais_shipxplorer_method"].list_set(0, "station")
        envs["ais_shipxplorer_sharing_key"].list_set(0, "  a-sharing-key  ")
        envs["ais_shipxplorer_serial_number"].list_set(0, " SXTRPI001234\n")

        adsb_im.update_shipxplorer_config()

        assert envs["ais_shipxplorer_sharing_key"].list_get(0) == "a-sharing-key"
        assert envs["ais_shipxplorer_serial_number"].list_get(0) == "SXTRPI001234"


class TestShipXplorerDiagnostics:
    """Share Diagnostics ships config.json and .env, so the credentials must be sanitized"""

    def test_credentials_are_in_the_sanitizer(self):
        sanitizer = (ADSB_ROOT / "scripts" / "search-replace.py").read_text()

        assert '"AIS_SHIPXPLORER_SHARING_KEY"' in sanitizer
        assert '"AIS_SHIPXPLORER_SERIAL_NUMBER"' in sanitizer
