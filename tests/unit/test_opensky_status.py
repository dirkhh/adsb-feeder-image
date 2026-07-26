"""Tests for OpenSky receiver status reporting."""

from unittest.mock import MagicMock, patch

import pytest
from utils.agg_status import AggStatus, T


def make_status(serial="-1408237521"):
    data = MagicMock()
    data.netconfigs = {}
    data.env_by_tags.return_value.list_get.return_value = serial
    system = MagicMock()
    system.getContainerStatus.return_value = "up"
    return AggStatus("opensky", 0, data, "http://127.0.0.1", system)


@pytest.mark.parametrize(
    ("sample_age", "messages_per_minute", "expected"),
    [
        (60, 100, T.Good),
        (60, 0, T.Warning),
        (600, 100, T.Warning),
        (1801, 100, T.Disconnected),
    ],
)
def test_status_uses_sensor_page_thresholds(sample_age, messages_per_minute, expected):
    now = 2_000_000_000
    serial = "-1408237521"
    status = make_status(serial)
    status.get_json = MagicMock(return_value=({"series": {serial: [[(now - sample_age) * 1000, messages_per_minute]]}}, 200))

    with patch("utils.agg_status.time.time", return_value=now):
        status.get_opensky_data_status()

    assert status._beast == expected


def test_status_distinguishes_offline_from_api_failure():
    offline = make_status()
    offline.get_json = MagicMock(return_value=({"series": {}}, 200))
    unavailable = make_status()
    unavailable.get_json = MagicMock(return_value=(None, -1))

    with patch("utils.agg_status.time.time", return_value=2_000_000_000):
        offline.get_opensky_data_status()
        unavailable.get_opensky_data_status()

    assert offline._beast == T.Disconnected
    assert unavailable._beast == T.Unknown


def test_status_skips_request_without_serial():
    status = make_status(serial="")
    status.get_json = MagicMock()

    with patch("utils.agg_status.time.time", return_value=2_000_000_000):
        status.get_opensky_data_status()

    assert status._beast == T.Unknown
    status.get_json.assert_not_called()


def test_status_is_cached_for_one_minute():
    now = 2_000_000_000
    serial = "-1408237521"
    status = make_status(serial)
    status.get_json = MagicMock(return_value=({"series": {serial: [[now * 1000, 100]]}}, 200))

    with patch("utils.agg_status.time.time", side_effect=[now, now + 30]):
        status.get_opensky_data_status()
        status.get_opensky_data_status()

    status.get_json.assert_called_once()
