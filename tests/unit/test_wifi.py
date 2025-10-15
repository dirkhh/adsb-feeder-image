"""
Tests for utils.wifi module
"""
import pytest
from unittest.mock import patch, MagicMock, call
import subprocess
import time

from utils.wifi import Wifi


class TestWifiClass:
    """Test the Wifi class"""

    def test_wifi_initialization_dietpi(self):
        """Test Wifi initialization on DietPi"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/boot/dietpi"

            wifi = Wifi("wlan0")

            assert wifi.baseos == "dietpi"
            assert wifi.wlan == "wlan0"

    def test_wifi_initialization_raspbian(self):
        """Test Wifi initialization on Raspbian"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"

            wifi = Wifi("wlan1")

            assert wifi.baseos == "raspbian"
            assert wifi.wlan == "wlan1"

    def test_wifi_initialization_unknown(self):
        """Test Wifi initialization on unknown OS"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False

            wifi = Wifi("wlan0")

            assert wifi.baseos == "unknown"
            assert wifi.wlan == "wlan0"

    @patch('subprocess.run')
    def test_get_ssid_success(self, mock_subprocess):
        """Test successful SSID retrieval"""
        mock_result = MagicMock()
        mock_result.stdout = b"TestNetwork\n"
        mock_subprocess.return_value = mock_result

        wifi = Wifi()

        ssid = wifi.get_ssid()

        assert ssid == "TestNetwork"
        mock_subprocess.assert_called_once_with(
            "iwgetid -r",
            shell=True,
            capture_output=True,
            timeout=2.0
        )

    @patch('subprocess.run')
    def test_get_ssid_empty(self, mock_subprocess):
        """Test SSID retrieval when not connected"""
        mock_result = MagicMock()
        mock_result.stdout = b"\n"
        mock_subprocess.return_value = mock_result

        wifi = Wifi()

        ssid = wifi.get_ssid()

        assert ssid == ""

    @patch('subprocess.run')
    def test_get_ssid_exception(self, mock_subprocess):
        """Test SSID retrieval with exception"""
        mock_subprocess.side_effect = Exception("Network error")

        wifi = Wifi()

        ssid = wifi.get_ssid()

        assert ssid == ""

    @patch('utils.wifi.run_shell_captured')
    @patch('time.time')
    @patch('time.sleep')
    def test_wait_wpa_supplicant_success(self, mock_sleep, mock_time, mock_run_shell):
        """Test successful wpa_supplicant wait"""
        # Mock time progression
        mock_time.side_effect = [0, 1, 2, 3]  # 3 seconds total

        # Mock successful wpa_supplicant check
        mock_run_shell.return_value = (True, "1234")

        wifi = Wifi()

        result = wifi.wait_wpa_supplicant()

        assert result is True
        mock_run_shell.assert_called_with("pgrep wpa_supplicant", timeout=5)
        mock_sleep.assert_called_with(1)

    @patch('utils.wifi.run_shell_captured')
    @patch('time.time')
    @patch('time.sleep')
    def test_wait_wpa_supplicant_timeout(self, mock_sleep, mock_time, mock_run_shell):
        """Test wpa_supplicant wait timeout"""
        # Mock time progression (46 seconds to trigger timeout)
        # Use a counter to track calls and return incrementing values
        call_count = {'value': 0}
        def time_side_effect():
            result = call_count['value']
            call_count['value'] += 1
            return result
        mock_time.side_effect = time_side_effect

        # Mock failed wpa_supplicant check
        mock_run_shell.return_value = (False, "")

        wifi = Wifi()

        result = wifi.wait_wpa_supplicant()

        assert result is False
        # Should have called pgrep multiple times
        assert mock_run_shell.call_count > 40

    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    def test_wpa_cli_reconfigure_success(self, mock_popen, mock_set_blocking, mock_sleep, mock_time):
        """Test successful wpa_cli reconfigure"""
        # Mock time progression
        mock_time.side_effect = [0, 0.1, 0.2, 0.3, 0.4, 0.5]

        # Mock successful wpa_cli process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [
            ">",  # Prompt indicating ready
            "reconfigure\n",  # Echo of command
            "<3>CTRL-EVENT-CONNECTED\n",  # Connection event
            ""  # EOF
        ]
        mock_popen.return_value = mock_process

        wifi = Wifi()

        result = wifi.wpa_cli_reconfigure()

        assert result is True
        mock_popen.assert_called_once()

    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    def test_wpa_cli_reconfigure_timeout(self, mock_popen, mock_set_blocking, mock_sleep, mock_time):
        """Test wpa_cli reconfigure timeout"""
        # Mock time progression to exceed 20 second timeout
        call_count = {'value': 0}
        def time_side_effect():
            result = call_count['value']
            call_count['value'] += 0.5
            return result
        mock_time.side_effect = time_side_effect

        # Mock process that never connects
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = ""  # No output
        mock_popen.return_value = mock_process

        wifi = Wifi()

        result = wifi.wpa_cli_reconfigure()

        assert result is False

    @patch('subprocess.Popen')
    def test_wpa_cli_reconfigure_exception(self, mock_popen):
        """Test wpa_cli reconfigure with exception"""
        mock_popen.side_effect = Exception("Process error")

        wifi = Wifi()

        result = wifi.wpa_cli_reconfigure()

        assert result is False

    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    def test_wpa_cli_scan_success(self, mock_popen, mock_set_blocking, mock_sleep, mock_time):
        """Test successful wpa_cli_scan"""
        # Mock time progression - need enough values for both loops
        mock_time.side_effect = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

        # Mock successful wpa_cli scan process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [
            "Interactive mode\n",
            "<3>CTRL-EVENT-SCAN-RESULTS\n",
            "bssid / frequency / signal level / flags / ssid\n",
            "00:11:22:33:44:55\t2412\t-30\t[WPA2-PSK-CCMP][ESS]\tTestNetwork1\n",
            "66:77:88:99:aa:bb\t2437\t-45\t[WPA2-PSK-CCMP][ESS]\tTestNetwork2\n",
            ""
        ]
        mock_popen.return_value = mock_process

        wifi = Wifi()

        ssids = wifi.wpa_cli_scan()

        assert "TestNetwork1" in ssids
        assert "TestNetwork2" in ssids
        assert len(ssids) == 2

    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    def test_wpa_cli_scan_timeout(self, mock_popen, mock_set_blocking, mock_sleep, mock_time):
        """Test wpa_cli_scan timeout"""
        # Mock time progression to exceed 15 second timeout
        call_count = {'value': 0}
        def time_side_effect():
            result = call_count['value']
            call_count['value'] += 1
            return result
        mock_time.side_effect = time_side_effect

        # Mock process that never returns scan results
        mock_process = MagicMock()
        mock_process.stdout.readline.return_value = ""
        mock_popen.return_value = mock_process

        wifi = Wifi()

        ssids = wifi.wpa_cli_scan()

        assert ssids == []

    @patch('subprocess.Popen')
    def test_wpa_cli_scan_exception(self, mock_popen):
        """Test wpa_cli_scan with exception"""
        mock_popen.side_effect = Exception("Process error")

        wifi = Wifi()

        ssids = wifi.wpa_cli_scan()

        assert ssids == []

    @patch('subprocess.run')
    def test_scan_ssids_raspbian_success(self, mock_subprocess):
        """Test successful scan_ssids on Raspbian"""
        mock_result = MagicMock()
        mock_result.stdout = b"TestNetwork1\nTestNetwork2\n--\nTestNetwork3\nTestNetwork1\n"
        mock_subprocess.return_value = mock_result

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
            wifi = Wifi()

        wifi.scan_ssids()

        # scan_ssids sets self.ssids attribute
        assert "TestNetwork1" in wifi.ssids
        assert "TestNetwork2" in wifi.ssids
        assert "TestNetwork3" in wifi.ssids
        # Should filter out duplicates and "--"
        assert wifi.ssids.count("TestNetwork1") == 1
        assert "--" not in wifi.ssids

    @patch('subprocess.run')
    def test_scan_ssids_raspbian_empty(self, mock_subprocess):
        """Test scan_ssids on Raspbian with no networks"""
        mock_result = MagicMock()
        mock_result.stdout = b"\n"
        mock_subprocess.return_value = mock_result

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
            wifi = Wifi()

        wifi.scan_ssids()

        # scan_ssids doesn't set ssids for empty results
        assert not hasattr(wifi, 'ssids') or wifi.ssids == []

    @patch('subprocess.run')
    def test_scan_ssids_raspbian_exception(self, mock_subprocess):
        """Test scan_ssids on Raspbian with exception"""
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, "nmcli")

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
            wifi = Wifi()

        result = wifi.scan_ssids()

        # Should return None on exception (based on code)
        assert result is None

    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    def test_scan_ssids_dietpi_success(self, mock_popen, mock_set_blocking, mock_sleep, mock_time):
        """Test successful scan_ssids on DietPi (uses wpa_cli_scan)"""
        # Mock time progression - need enough values for both loops
        mock_time.side_effect = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

        # Mock successful wpa_cli scan process
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [
            "Interactive mode\n",
            "<3>CTRL-EVENT-SCAN-RESULTS\n",
            "bssid / frequency / signal level / flags / ssid\n",
            "00:11:22:33:44:55\t2412\t-30\t[WPA2-PSK-CCMP][ESS]\tDietPiNetwork1\n",
            ""
        ]
        mock_popen.return_value = mock_process

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/boot/dietpi"
            wifi = Wifi()

        wifi.scan_ssids()

        # scan_ssids sets self.ssids attribute
        assert "DietPiNetwork1" in wifi.ssids

    @patch('subprocess.run')
    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    @patch('utils.wifi.run_shell_captured')
    @patch('builtins.open', new_callable=MagicMock)
    @patch('os.rename')
    @patch('os.remove')
    def test_wifi_connect_dietpi_success(self, mock_remove, mock_rename, mock_open, mock_run_shell,
                                         mock_popen, mock_set_blocking, mock_sleep, mock_time,
                                         mock_subprocess):
        """Test successful wifi_connect on DietPi"""
        # Mock time progression - need enough values for wait_wpa_supplicant and wpa_cli_reconfigure
        mock_time.side_effect = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

        # Mock wpa_passphrase subprocess
        mock_result = MagicMock()
        mock_result.stdout = b"""network={
        ssid="TestNetwork"
        psk=abc123
}"""
        mock_subprocess.return_value = mock_result

        # Mock file reading for dietpi_add_wifi_hotplug
        mock_file = MagicMock()
        mock_file.__enter__.return_value.readlines.return_value = [
            "#allow-hotplug wlan0\n",
            "iface wlan0 inet dhcp\n"
        ]
        mock_open.return_value = mock_file

        # Mock wait_wpa_supplicant
        mock_run_shell.return_value = (True, "1234")

        # Mock wpa_cli_reconfigure
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [
            ">",
            "reconfigure\n",
            "<3>CTRL-EVENT-CONNECTED\n",
            ""
        ]
        mock_popen.return_value = mock_process

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/boot/dietpi"
            wifi = Wifi()
            result = wifi.wifi_connect("TestNetwork", "password123", "US")

        assert result is True

    @patch('subprocess.run')
    @patch('time.time')
    @patch('time.sleep')
    def test_wifi_connect_raspbian_success(self, mock_sleep, mock_time, mock_subprocess):
        """Test successful wifi_connect on Raspbian"""
        # Mock time progression
        mock_time.side_effect = [0, 1, 2, 3]

        # Mock scan_ssids (nmcli scan)
        scan_result = MagicMock()
        scan_result.stdout = b"TestNetwork\n"

        # Mock nmcli connect
        connect_result = MagicMock()
        connect_result.stdout = b"Connection successfully activated\n"
        connect_result.stderr = b""

        mock_subprocess.side_effect = [scan_result, connect_result]

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
            wifi = Wifi()

        result = wifi.wifi_connect("TestNetwork", "password123", "US")

        assert result is True

    @patch('subprocess.run')
    @patch('time.time')
    @patch('time.sleep')
    def test_wifi_connect_raspbian_failure(self, mock_sleep, mock_time, mock_subprocess):
        """Test wifi_connect failure on Raspbian"""
        # Mock time progression to exceed retry timeout
        call_count = {'value': 0}
        def time_side_effect():
            result = call_count['value']
            call_count['value'] += 5
            return result
        mock_time.side_effect = time_side_effect

        # Mock scan_ssids
        scan_result = MagicMock()
        scan_result.stdout = b"TestNetwork\n"

        # Mock nmcli connect failure
        connect_result = MagicMock()
        connect_result.stdout = b"Error: Connection failed\n"
        connect_result.stderr = b""

        mock_subprocess.side_effect = [scan_result, connect_result, connect_result, connect_result]

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
            wifi = Wifi()

        result = wifi.wifi_connect("TestNetwork", "wrongpassword", "US")

        assert result is False

    def test_wifi_connect_unknown_os(self):
        """Test wifi_connect on unknown OS returns False"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            wifi = Wifi()

        result = wifi.wifi_connect("TestNetwork", "password123", "US")

        assert result is False


class TestWifiIntegration:
    """Integration tests for WiFi functionality"""

    @patch('os.path.exists')
    def test_wifi_os_detection_integration(self, mock_exists):
        """Test WiFi OS detection integration"""
        # Test DietPi detection
        mock_exists.side_effect = lambda path: path == "/boot/dietpi"
        wifi_dietpi = Wifi()
        assert wifi_dietpi.baseos == "dietpi"

        # Test Raspbian detection
        mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
        wifi_raspbian = Wifi()
        assert wifi_raspbian.baseos == "raspbian"

        # Test unknown OS - must clear side_effect first
        mock_exists.side_effect = None
        mock_exists.return_value = False
        wifi_unknown = Wifi()
        assert wifi_unknown.baseos == "unknown"

    @patch('subprocess.run')
    def test_wifi_full_workflow_raspbian(self, mock_subprocess):
        """Test complete WiFi workflow on Raspbian"""
        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
            wifi = Wifi()

        # Mock SSID retrieval
        ssid_result = MagicMock()
        ssid_result.stdout = b"TestNetwork\n"
        mock_subprocess.return_value = ssid_result

        # Test getting current SSID
        current_ssid = wifi.get_ssid()
        assert current_ssid == "TestNetwork"

        # Mock network scan
        scan_result = MagicMock()
        scan_result.stdout = b"TestNetwork\nOtherNetwork\n"
        mock_subprocess.return_value = scan_result

        # Test scanning for networks
        wifi.scan_ssids()
        assert "TestNetwork" in wifi.ssids
        assert "OtherNetwork" in wifi.ssids

    @patch('subprocess.run')
    @patch('utils.wifi.run_shell_captured')
    @patch('time.time')
    @patch('time.sleep')
    @patch('os.set_blocking')
    @patch('subprocess.Popen')
    @patch('builtins.open', new_callable=MagicMock)
    @patch('os.rename')
    @patch('os.remove')
    def test_wifi_connection_workflow_dietpi(self, mock_remove, mock_rename, mock_open, mock_popen,
                                             mock_set_blocking, mock_sleep, mock_time,
                                             mock_run_shell, mock_subprocess):
        """Test WiFi connection workflow on DietPi"""
        # Mock time progression - enough for dietpi_add_wifi_hotplug, wait_wpa_supplicant, wpa_cli_reconfigure
        mock_time.side_effect = [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5]

        # Mock wpa_passphrase
        wpa_result = MagicMock()
        wpa_result.stdout = b'network={\n\tssid="TestNetwork"\n\tpsk=abc123\n}'
        mock_subprocess.return_value = wpa_result

        # Mock file reading for dietpi_add_wifi_hotplug
        mock_file = MagicMock()
        mock_file.__enter__.return_value.readlines.return_value = [
            "#allow-hotplug wlan0\n",
            "iface wlan0 inet dhcp\n"
        ]
        mock_open.return_value = mock_file

        # Mock wait_wpa_supplicant
        mock_run_shell.return_value = (True, "1234")

        # Mock wpa_cli_reconfigure
        mock_process = MagicMock()
        mock_process.stdout.readline.side_effect = [
            ">",
            "reconfigure\n",
            "<3>CTRL-EVENT-CONNECTED\n",
            ""
        ]
        mock_popen.return_value = mock_process

        with patch('os.path.exists') as mock_exists:
            mock_exists.side_effect = lambda path: path == "/boot/dietpi"
            wifi = Wifi()

        # Test connection
        result = wifi.wifi_connect("TestNetwork", "password123", "US")
        assert result is True

        # Test waiting for wpa_supplicant (reuse existing mock)
        result = wifi.wait_wpa_supplicant()
        assert result is True

    def test_wifi_error_handling_integration(self):
        """Test WiFi error handling integration"""
        wifi = Wifi()

        # Test SSID retrieval with exception
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.side_effect = Exception("Network error")
            ssid = wifi.get_ssid()
            assert ssid == ""

        # Test scan with failure on Raspbian
        with patch('subprocess.run') as mock_subprocess:
            with patch('os.path.exists') as mock_exists:
                mock_exists.side_effect = lambda path: path == "/etc/rpi-issue"
                mock_subprocess.side_effect = subprocess.CalledProcessError(1, "nmcli")
                wifi_raspbian = Wifi()
                result = wifi_raspbian.scan_ssids()
                assert result is None

        # Test wifi_connect on unknown OS
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = False
            wifi_unknown = Wifi()
            result = wifi_unknown.wifi_connect("TestNetwork", "password")
            assert result is False
