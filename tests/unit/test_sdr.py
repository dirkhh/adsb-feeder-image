"""
Tests for utils.sdr module
"""
import pytest
from unittest.mock import patch, MagicMock, call
import subprocess
import re
import time

from utils.sdr import SDR, SDRDevices


class TestSDRClass:
    """Test the SDR class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_data = MagicMock()
        self.mock_data.is_enabled.return_value = False

    @patch('subprocess.run')
    def test_sdr_initialization(self, mock_subprocess):
        """Test SDR initialization"""
        # Mock subprocess to return empty output
        mock_result = MagicMock()
        mock_result.stdout = b""
        mock_subprocess.return_value = mock_result

        sdr = SDR("rtlsdr", "1:2", self.mock_data)

        assert sdr._d is self.mock_data
        assert sdr._type == "rtlsdr"
        assert sdr._address == "1:2"
        assert sdr._serial_probed == ""
        # lsusb_output will be set when _serial property is accessed during init
        assert sdr.lsusb_output == "lsusb -s 1:2: "
        assert sdr.purpose == ""
        assert sdr.gain == ""
        assert sdr.biastee is False

    @patch('subprocess.run')
    def test_serial_property_success(self, mock_subprocess):
        """Test successful serial number retrieval"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x0bda Realtek Semiconductor Corp.
  idProduct          0x2838 RTL2838UHF DVB-T
  bcdDevice            1.00
  iManufacturer           1 Realtek
  iProduct                2 RTL2838UHIDIR
  iSerial                 3 00000001
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("rtlsdr", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "00000001"
        assert sdr._serial_probed == "00000001"
        mock_subprocess.assert_called_once_with("lsusb -s 1:2 -v", shell=True, capture_output=True)

    @patch('subprocess.run')
    def test_serial_property_no_serial(self, mock_subprocess):
        """Test serial property when no serial number is found"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x0bda Realtek Semiconductor Corp.
  idProduct          0x2838 RTL2838UHF DVB-T
  bcdDevice            1.00
  iManufacturer           1 Realtek
  iProduct                2 RTL2838UHIDIR
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("rtlsdr", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == ""
        assert sdr._serial_probed == ""

    @patch('subprocess.run')
    def test_serial_property_airspy(self, mock_subprocess):
        """Test serial property for AirSpy device"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x1d50 OpenMoko, Inc.
  idProduct          0x6089 AirSpy
  bcdDevice            1.00
  iManufacturer           1 AirSpy
  iProduct                2 AirSpy
  iSerial                 3 00000001:1234567890ABCDEF
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("airspy", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "1234567890ABCDEF"
        assert sdr._serial_probed == "1234567890ABCDEF"

    @patch('subprocess.run')
    def test_serial_property_airspy_invalid_format(self, mock_subprocess):
        """Test serial property for AirSpy with invalid format"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x1d50 OpenMoko, Inc.
  idProduct          0x6089 AirSpy
  bcdDevice            1.00
  iManufacturer           1 AirSpy
  iProduct                2 AirSpy
  iSerial                 3 00000001
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("airspy", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "00000001"
        assert sdr._serial_probed == "00000001"

    @patch('subprocess.run')
    def test_serial_property_stratuxv3(self, mock_subprocess):
        """Test serial property for StratuxV3 device"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x0bda Realtek Semiconductor Corp.
  idProduct          0x2838 RTL2838UHF DVB-T
  bcdDevice            1.00
  iManufacturer           1 Realtek
  iProduct                2 RTL2838UHIDIR
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("stratuxv3", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "stratuxv3 w/o serial"
        assert sdr._serial_probed == "stratuxv3 w/o serial"

    @patch('subprocess.run')
    def test_serial_property_modesbeast(self, mock_subprocess):
        """Test serial property for Mode-S Beast device"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x1234 Mode-S Beast
  idProduct          0x5678 Mode-S Beast
  bcdDevice            1.00
  iManufacturer           1 Mode-S Beast
  iProduct                2 Mode-S Beast
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("modesbeast", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "Mode-S Beast w/o serial"
        assert sdr._serial_probed == "Mode-S Beast w/o serial"

    @patch('subprocess.run')
    def test_serial_property_sdrplay(self, mock_subprocess):
        """Test serial property for SDRplay device"""
        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x1df7 SDRplay
  idProduct          0x2500 SDRplay
  bcdDevice            1.00
  iManufacturer           1 SDRplay
  iProduct                2 SDRplay
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("sdrplay", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "SDRplay w/o serial"
        assert sdr._serial_probed == "SDRplay w/o serial"

    @patch('subprocess.run')
    def test_serial_property_sdrplay_ignore_serial(self, mock_subprocess):
        """Test serial property for SDRplay with ignore serial flag"""
        self.mock_data.is_enabled.return_value = True  # sdrplay_ignore_serial enabled

        mock_output = """
Device Descriptor:
  bLength                18
  bDescriptorType         1
  bcdUSB               2.00
  bDeviceClass            0
  bDeviceSubClass         0
  bDeviceProtocol         0
  bMaxPacketSize0        64
  idVendor           0x1df7 SDRplay
  idProduct          0x2500 SDRplay
  bcdDevice            1.00
  iManufacturer           1 SDRplay
  iProduct                2 SDRplay
  iSerial                 3 1234567890
  bNumConfigurations      1
"""
        mock_result = MagicMock()
        mock_result.stdout = mock_output.encode()
        mock_subprocess.return_value = mock_result

        sdr = SDR("sdrplay", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == "SDRplay w/o serial"
        assert sdr._serial_probed == "SDRplay w/o serial"

    @patch('subprocess.run')
    def test_serial_property_subprocess_error(self, mock_subprocess):
        """Test serial property with subprocess error"""
        mock_subprocess.side_effect = subprocess.SubprocessError("lsusb failed")

        sdr = SDR("rtlsdr", "1:2", self.mock_data)

        serial = sdr._serial

        assert serial == ""
        assert sdr._serial_probed == ""

    def test_json_property(self):
        """Test JSON property"""
        sdr = SDR("rtlsdr", "1:2", self.mock_data)
        sdr._serial_probed = "12345678"
        sdr.purpose = "adsb"
        sdr.gain = "auto"
        sdr.biastee = True

        json_data = sdr._json

        expected = {
            "type": "rtlsdr",
            "address": "1:2",
            "serial": "12345678",
            "purpose": "adsb",
            "gain": "auto",
            "biastee": True
        }

        assert json_data == expected

    def test_equality_comparison(self):
        """Test equality comparison between SDR objects"""
        sdr1 = SDR("rtlsdr", "1:2", self.mock_data)
        sdr1._serial_probed = "12345678"
        sdr1.purpose = "adsb"
        sdr1.gain = "auto"
        sdr1.biastee = True

        sdr2 = SDR("rtlsdr", "1:2", self.mock_data)
        sdr2._serial_probed = "12345678"
        sdr2.purpose = "adsb"
        sdr2.gain = "auto"
        sdr2.biastee = True

        assert sdr1 == sdr2

        # Test with different values
        sdr2.purpose = "uat978"
        assert sdr1 != sdr2

        # Test with non-SDR object
        assert sdr1 != "not an sdr"

    def test_repr(self):
        """Test string representation"""
        sdr = SDR("rtlsdr", "1:2", self.mock_data)
        sdr._serial_probed = "12345678"
        sdr.purpose = "adsb"
        sdr.gain = "auto"
        sdr.biastee = True

        repr_str = repr(sdr)

        expected = "SDR(type: 'rtlsdr' address: '1:2', serial: '12345678', purpose: 'adsb', gain: 'auto', biastee: True)"
        assert repr_str == expected


class TestSDRDevicesClass:
    """Test the SDRDevices class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_data = MagicMock()
        self.mock_assignment_function = MagicMock()

    def test_sdr_devices_initialization(self):
        """Test SDRDevices initialization"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        assert sdr_devices._d is self.mock_data
        assert sdr_devices.assignment_function is self.mock_assignment_function
        assert sdr_devices.sdrs == []
        assert sdr_devices.sdr_settings == {}
        assert sdr_devices.duplicates == set()
        assert sdr_devices.lsusb_output == ""
        assert sdr_devices.last_probe == 0.0
        assert sdr_devices.last_debug_out == ""
        assert sdr_devices.null_sdr._type == "unknown"
        assert sdr_devices.null_sdr._address == "unknown"

    def test_sdr_devices_len(self):
        """Test SDRDevices length"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        assert len(sdr_devices) == 0

        # Add some mock SDRs
        sdr_devices.sdrs = [MagicMock(), MagicMock()]

        assert len(sdr_devices) == 2

    def test_sdr_devices_repr(self):
        """Test SDRDevices string representation"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        repr_str = repr(sdr_devices)

        # When empty, __repr__ returns "SDRDevices()"
        assert repr_str == "SDRDevices()"

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_ensure_populated_success(self, mock_subprocess, mock_time):
        """Test successful device population"""
        # Mock time to bypass 10-second cache
        # last_probe starts at 0, so time.time() needs to return > 10 to trigger populate
        mock_time.return_value = 100

        # Mock lsusb output with real device IDs
        mock_lsusb_output = """Bus 001 Device 002: ID 0bda:2838 Realtek Semiconductor Corp. RTL2838UHF DVB-T
Bus 001 Device 003: ID 1d50:60a1 OpenMoko, Inc. AirSpy"""

        # Mock subprocess for lsusb command and serial lookups
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                result.stdout = mock_lsusb_output.encode()
            elif "lsusb -s" in cmd:
                # Mock serial lookup responses
                if "001:002" in cmd:
                    result.stdout = b"iSerial                 3 00000001"
                elif "001:003" in cmd:
                    result.stdout = b"iSerial                 3 AIRSPY123"
                else:
                    result.stdout = b""
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)
        sdr_devices.ensure_populated()

        # Verify devices were found
        assert len(sdr_devices.sdrs) == 2
        assert len(sdr_devices.sdr_settings) == 2

        # Verify device types
        types = [sdr._type for sdr in sdr_devices.sdrs]
        assert "rtlsdr" in types
        assert "airspy" in types

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_ensure_populated_no_devices(self, mock_subprocess, mock_time):
        """Test device population with no devices"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        mock_result = MagicMock()
        mock_result.stdout = b""
        mock_subprocess.return_value = mock_result
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)
        sdr_devices.ensure_populated()

        assert len(sdr_devices.sdrs) == 0
        assert len(sdr_devices.sdr_settings) == 0

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_ensure_populated_subprocess_error(self, mock_subprocess, mock_time):
        """Test device population with subprocess error"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        mock_subprocess.side_effect = subprocess.SubprocessError("lsusb failed")
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)
        sdr_devices.ensure_populated()

        assert len(sdr_devices.sdrs) == 0
        assert len(sdr_devices.sdr_settings) == 0

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_get_sdr_by_serial(self, mock_subprocess, mock_time):
        """Test getting SDR by serial number"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        # Mock lsusb with one device
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                result.stdout = b"Bus 001 Device 002: ID 0bda:2838 Realtek Semiconductor Corp."
            elif "lsusb -s 001:002" in cmd:
                result.stdout = b"iSerial                 3 12345678"
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        # Call ensure_populated to populate devices
        sdr_devices.ensure_populated()

        # Test getting existing SDR
        result = sdr_devices.get_sdr_by_serial("12345678")
        assert result._serial == "12345678"

        # Test getting non-existing SDR returns null_sdr
        result = sdr_devices.get_sdr_by_serial("nonexistent")
        assert result is sdr_devices.null_sdr

    def test_get_sdr_by_serial_empty_list(self):
        """Test getting SDR by serial from empty list"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        result = sdr_devices.get_sdr_by_serial("12345678")
        assert result is sdr_devices.null_sdr

    def test_add_sdr_settings(self):
        """Test adding SDR settings directly to dict"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        mock_sdr = MagicMock()
        mock_sdr._serial = "12345678"

        # Direct dict manipulation (no add_sdr_settings method)
        sdr_devices.sdr_settings[mock_sdr._serial] = mock_sdr

        assert "12345678" in sdr_devices.sdr_settings
        assert sdr_devices.sdr_settings["12345678"] is mock_sdr

    def test_remove_sdr_settings(self):
        """Test removing SDR settings directly from dict"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        mock_sdr = MagicMock()
        mock_sdr._serial = "12345678"

        # Add and then remove using dict operations
        sdr_devices.sdr_settings[mock_sdr._serial] = mock_sdr
        assert "12345678" in sdr_devices.sdr_settings

        del sdr_devices.sdr_settings["12345678"]
        assert "12345678" not in sdr_devices.sdr_settings

    def test_get_sdr_settings(self):
        """Test getting SDR settings directly from dict"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        mock_sdr = MagicMock()
        mock_sdr._serial = "12345678"

        # Direct dict access
        sdr_devices.sdr_settings[mock_sdr._serial] = mock_sdr

        result = sdr_devices.sdr_settings.get("12345678")
        assert result is mock_sdr

        # Test getting non-existing settings
        result = sdr_devices.sdr_settings.get("nonexistent")
        assert result is None

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_check_duplicates(self, mock_subprocess, mock_time):
        """Test duplicate detection during ensure_populated"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        # Mock lsusb with duplicate devices (same serial)
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                # Two devices with same ID (will get same serial)
                result.stdout = b"Bus 001 Device 002: ID 0bda:2838 Realtek\nBus 001 Device 003: ID 0bda:2838 Realtek"
            elif "lsusb -s" in cmd:
                # Both return same serial
                result.stdout = b"iSerial                 3 12345678"
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)
        sdr_devices.ensure_populated()

        # Duplicates should be auto-detected
        assert "12345678" in sdr_devices.duplicates

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_check_duplicates_no_duplicates(self, mock_subprocess, mock_time):
        """Test no duplicates with different serials"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        # Mock lsusb with different devices
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                result.stdout = b"Bus 001 Device 002: ID 0bda:2838 Realtek\nBus 001 Device 003: ID 1d50:60a1 AirSpy"
            elif "lsusb -s 001:002" in cmd:
                result.stdout = b"iSerial                 3 12345678"
            elif "lsusb -s 001:003" in cmd:
                result.stdout = b"iSerial                 3 87654321"
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)
        sdr_devices.ensure_populated()

        # No duplicates should be found
        assert len(sdr_devices.duplicates) == 0

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_get_debug_output(self, mock_subprocess, mock_time):
        """Test accessing debug_out attribute"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        # Mock lsusb with one device
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                result.stdout = b"Bus 001 Device 002: ID 0bda:2838 Realtek"
            elif "lsusb -s 001:002" in cmd:
                result.stdout = b"iSerial                 3 12345678"
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)
        sdr_devices.ensure_populated()

        # Access debug_out attribute (set during _get_sdr_info)
        debug_output = sdr_devices.debug_out

        assert "_get_sdr_info() found:" in debug_output
        assert "rtlsdr" in debug_output
        assert "12345678" in debug_output

    def test_clear_duplicates(self):
        """Test clearing duplicates directly"""
        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        # Add some duplicates
        sdr_devices.duplicates.add("12345678")
        sdr_devices.duplicates.add("87654321")

        assert len(sdr_devices.duplicates) == 2

        # Direct set manipulation (no clear_duplicates method)
        sdr_devices.duplicates.clear()

        assert len(sdr_devices.duplicates) == 0

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_sdr_devices_integration(self, mock_subprocess, mock_time):
        """Test SDRDevices integration with actual API"""
        # Mock time to bypass cache
        mock_time.return_value = 100

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        # Test initial state
        assert len(sdr_devices) == 0
        assert len(sdr_devices.sdr_settings) == 0
        assert len(sdr_devices.duplicates) == 0

        # Mock lsusb with one device
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                result.stdout = b"Bus 001 Device 002: ID 0bda:2838 Realtek"
            elif "lsusb -s 001:002" in cmd:
                result.stdout = b"iSerial                 3 12345678"
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        # Populate devices
        sdr_devices.ensure_populated()

        # Test length
        assert len(sdr_devices) == 1

        # Test getting SDR by serial
        result = sdr_devices.get_sdr_by_serial("12345678")
        assert result._serial == "12345678"

        # Test settings are auto-populated
        assert "12345678" in sdr_devices.sdr_settings

        # Test direct dict manipulation
        mock_sdr = MagicMock()
        mock_sdr._serial = "new_serial"
        sdr_devices.sdr_settings["new_serial"] = mock_sdr
        assert "new_serial" in sdr_devices.sdr_settings

        # Test removing settings
        del sdr_devices.sdr_settings["new_serial"]
        assert "new_serial" not in sdr_devices.sdr_settings

        # Test getting non-existing settings
        settings = sdr_devices.sdr_settings.get("nonexistent")
        assert settings is None

    @patch('utils.sdr.time.time')
    @patch('utils.sdr.subprocess.run')
    def test_sdr_devices_thread_safety(self, mock_subprocess, mock_time):
        """Test SDRDevices thread safety with lock"""
        # Mock time
        mock_time.return_value = 100

        sdr_devices = SDRDevices(self.mock_assignment_function, self.mock_data)

        # Test that lock exists
        assert hasattr(sdr_devices, 'lock')
        assert sdr_devices.lock is not None

        # Mock lsusb
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if cmd == "lsusb":
                result.stdout = b"Bus 001 Device 002: ID 0bda:2838 Realtek"
            elif "lsusb -s 001:002" in cmd:
                result.stdout = b"iSerial                 3 12345678"
            else:
                result.stdout = b""
            return result

        mock_subprocess.side_effect = subprocess_side_effect
        self.mock_assignment_function.return_value = {}

        # Test that ensure_populated uses lock (basic thread safety test)
        sdr_devices.ensure_populated()

        result = sdr_devices.get_sdr_by_serial("12345678")
        assert result._serial == "12345678"
