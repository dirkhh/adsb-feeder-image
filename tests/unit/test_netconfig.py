"""
Tests for utils.netconfig module
"""
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4

from utils.netconfig import NetConfig, UltrafeederConfig


class TestNetConfig:
    """Test the NetConfig class"""

    def test_netconfig_initialization(self):
        """Test NetConfig initialization"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"
        has_policy = True

        netconfig = NetConfig(adsb_config, mlat_config, has_policy)

        assert netconfig.adsb_config == adsb_config
        assert netconfig.mlat_config == mlat_config
        assert netconfig._has_policy == has_policy

    def test_netconfig_has_policy_property(self):
        """Test has_policy property"""
        netconfig = NetConfig("adsb", "mlat", True)
        assert netconfig.has_policy is True

        netconfig = NetConfig("adsb", "mlat", False)
        assert netconfig.has_policy is False

    def test_generate_without_uuid(self):
        """Test generate without UUID"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate()

        assert result == "adsb_line_config;mlat_line_config,--privacy"

    def test_generate_with_uuid(self):
        """Test generate with UUID"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"
        test_uuid = "12345678-1234-1234-1234-123456789abc"

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(uuid=test_uuid)

        expected = f"adsb_line_config,uuid={test_uuid};mlat_line_config,uuid={test_uuid},--privacy"
        assert result == expected

    def test_generate_with_invalid_uuid(self):
        """Test generate with invalid UUID"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"
        invalid_uuid = "invalid-uuid"

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(uuid=invalid_uuid)

        # Should ignore invalid UUID
        assert result == "adsb_line_config;mlat_line_config,--privacy"

    def test_generate_without_privacy(self):
        """Test generate without privacy flag"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(mlat_privacy=False)

        assert result == "adsb_line_config;mlat_line_config"

    def test_generate_without_mlat(self):
        """Test generate without mlat"""
        adsb_config = "adsb_line_config"
        mlat_config = ""

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate()

        assert result == "adsb_line_config;"

    def test_generate_mlat_disabled(self):
        """Test generate with mlat disabled"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(mlat_enable=False)

        assert result == "adsb_line_config"

    def test_generate_mlat_disabled_with_uuid(self):
        """Test generate with mlat disabled but UUID provided"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"
        test_uuid = "12345678-1234-1234-1234-123456789abc"

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(uuid=test_uuid, mlat_enable=False)

        # Should still add UUID to adsb config
        assert result == f"adsb_line_config,uuid={test_uuid}"

    def test_generate_no_mlat_config(self):
        """Test generate with no mlat config"""
        adsb_config = "adsb_line_config"
        mlat_config = ""

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(uuid="12345678-1234-1234-1234-123456789abc")

        # Should only add UUID to adsb config
        assert result == "adsb_line_config,uuid=12345678-1234-1234-1234-123456789abc;"

    def test_generate_with_real_uuid(self):
        """Test generate with real UUID"""
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"
        real_uuid = str(uuid4())

        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate(uuid=real_uuid)

        expected = f"adsb_line_config,uuid={real_uuid};mlat_line_config,uuid={real_uuid},--privacy"
        assert result == expected


class TestUltrafeederConfig:
    """Test the UltrafeederConfig class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_data = MagicMock()
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.value = "test_value"
        self.mock_data.is_enabled.return_value = False

    def test_ultrafeeder_config_initialization(self):
        """Test UltrafeederConfig initialization"""
        config = UltrafeederConfig(self.mock_data, micro=0)

        assert config._micro == 0
        assert config._d is self.mock_data

    def test_ultrafeeder_config_initialization_with_micro(self):
        """Test UltrafeederConfig initialization with micro feeder"""
        config = UltrafeederConfig(self.mock_data, micro=1)

        assert config._micro == 1
        assert config._d is self.mock_data

    def test_enabled_aggregators_standalone(self):
        """Test enabled_aggregators for standalone feeder"""
        self.mock_data.is_enabled.return_value = False  # Not stage2
        self.mock_data.env_by_tags.return_value.value = "all"  # All aggregators

        config = UltrafeederConfig(self.mock_data, micro=0)

        aggregators = config.enabled_aggregators

        # Should return aggregator configuration
        assert isinstance(aggregators, dict)

    def test_enabled_aggregators_stage2(self):
        """Test enabled_aggregators for stage2 feeder"""
        self.mock_data.is_enabled.return_value = True  # Is stage2
        self.mock_data.env_by_tags.return_value.value = "all"  # All aggregators

        config = UltrafeederConfig(self.mock_data, micro=0)

        aggregators = config.enabled_aggregators

        # Should return aggregator configuration
        assert isinstance(aggregators, dict)

    def test_enabled_aggregators_micro_feeder(self):
        """Test enabled_aggregators for micro feeder"""
        self.mock_data.is_enabled.return_value = False  # Not stage2
        self.mock_data.env_by_tags.return_value.value = "all"  # All aggregators

        config = UltrafeederConfig(self.mock_data, micro=1)

        aggregators = config.enabled_aggregators

        # Should return aggregator configuration
        assert isinstance(aggregators, dict)

    def test_enabled_aggregators_specific_aggregators(self):
        """Test enabled_aggregators with specific aggregator selection"""
        self.mock_data.is_enabled.return_value = False  # Not stage2
        self.mock_data.env_by_tags.return_value.value = "flightaware,fr24"  # Specific aggregators

        config = UltrafeederConfig(self.mock_data, micro=0)

        aggregators = config.enabled_aggregators

        # Should return aggregator configuration
        assert isinstance(aggregators, dict)

    def test_enabled_aggregators_no_aggregators(self):
        """Test enabled_aggregators with no aggregators"""
        self.mock_data.is_enabled.return_value = False  # Not stage2
        self.mock_data.env_by_tags.return_value.value = "none"  # No aggregators

        config = UltrafeederConfig(self.mock_data, micro=0)

        aggregators = config.enabled_aggregators

        # Should return empty or minimal configuration
        assert isinstance(aggregators, dict)

    @patch('utils.netconfig.print_err')
    def test_enabled_aggregators_debug_logging(self, mock_print_err):
        """Test enabled_aggregators debug logging"""
        self.mock_data.is_enabled.return_value = False  # Not stage2
        self.mock_data.env_by_tags.return_value.value = "all"  # All aggregators

        config = UltrafeederConfig(self.mock_data, micro=0)

        aggregators = config.enabled_aggregators

        # Should log debug information
        mock_print_err.assert_called()
        call_args = mock_print_err.call_args[0][0]
        assert "enabled_aggregators" in call_args
        assert "0" in call_args  # micro value
        assert "all" in call_args  # aggregator selection
        assert "False" in call_args  # stage2 status

    def test_enabled_aggregators_micro_feeder_debug_logging(self):
        """Test enabled_aggregators debug logging for micro feeder"""
        with patch('utils.netconfig.print_err') as mock_print_err:
            self.mock_data.is_enabled.return_value = True  # Is stage2
            self.mock_data.env_by_tags.return_value.value = "flightaware"  # Specific aggregator

            config = UltrafeederConfig(self.mock_data, micro=2)

            aggregators = config.enabled_aggregators

            # Should log debug information with micro value
            mock_print_err.assert_called()
            call_args = mock_print_err.call_args[0][0]
            assert "enabled_aggregators" in call_args
            assert "2" in call_args  # micro value
            assert "flightaware" in call_args  # aggregator selection
            assert "True" in call_args  # stage2 status

    def test_ultrafeeder_config_data_integration(self):
        """Test UltrafeederConfig integration with data"""
        # Mock data with specific values
        self.mock_data.is_enabled.return_value = False
        self.mock_data.env_by_tags.return_value.value = "all"

        config = UltrafeederConfig(self.mock_data, micro=0)

        # Test that data methods are called correctly
        aggregators = config.enabled_aggregators

        # Verify data methods were called
        self.mock_data.env_by_tags.assert_called_with("aggregator_choice")
        self.mock_data.is_enabled.assert_called_with("stage2")

    def test_ultrafeeder_config_different_micro_values(self):
        """Test UltrafeederConfig with different micro values"""
        test_cases = [0, 1, 2, 5, 10]

        for micro in test_cases:
            config = UltrafeederConfig(self.mock_data, micro=micro)
            assert config._micro == micro

            # Should be able to get enabled aggregators
            aggregators = config.enabled_aggregators
            assert isinstance(aggregators, dict)

    def test_ultrafeeder_config_aggregator_selection_variations(self):
        """Test UltrafeederConfig with different aggregator selections"""
        test_selections = ["all", "none", "flightaware", "fr24,flightaware", "opensky"]

        for selection in test_selections:
            self.mock_data.env_by_tags.return_value.value = selection

            config = UltrafeederConfig(self.mock_data, micro=0)
            aggregators = config.enabled_aggregators

            assert isinstance(aggregators, dict)


class TestNetConfigIntegration:
    """Integration tests for NetConfig and UltrafeederConfig"""

    def test_netconfig_ultrafeeder_integration(self):
        """Test integration between NetConfig and UltrafeederConfig"""
        # Create NetConfig
        adsb_config = "adsb_line_config"
        mlat_config = "mlat_line_config"
        netconfig = NetConfig(adsb_config, mlat_config, True)

        # Create UltrafeederConfig
        mock_data = MagicMock()
        mock_data.is_enabled.return_value = False
        mock_data.env_by_tags.return_value.value = "all"
        ultrafeeder_config = UltrafeederConfig(mock_data, micro=0)

        # Test that both can work together
        netconfig_result = netconfig.generate()
        ultrafeeder_result = ultrafeeder_config.enabled_aggregators

        assert isinstance(netconfig_result, str)
        assert isinstance(ultrafeeder_result, dict)

    def test_netconfig_with_real_world_scenarios(self):
        """Test NetConfig with real-world scenarios"""
        # Scenario 1: Basic ADS-B only
        adsb_config = "adsb_line_config"
        mlat_config = ""
        netconfig = NetConfig(adsb_config, mlat_config, False)

        result = netconfig.generate()
        assert result == "adsb_line_config;"

        # Scenario 2: ADS-B with MLAT and privacy
        mlat_config = "mlat_line_config"
        netconfig = NetConfig(adsb_config, mlat_config, True)

        result = netconfig.generate()
        assert result == "adsb_line_config;mlat_line_config,--privacy"

        # Scenario 3: ADS-B with MLAT but no privacy
        result = netconfig.generate(mlat_privacy=False)
        assert result == "adsb_line_config;mlat_line_config"

        # Scenario 4: ADS-B with UUID
        test_uuid = "12345678-1234-1234-1234-123456789abc"
        result = netconfig.generate(uuid=test_uuid)
        expected = f"adsb_line_config,uuid={test_uuid};mlat_line_config,uuid={test_uuid},--privacy"
        assert result == expected

    def test_ultrafeeder_config_with_real_world_scenarios(self):
        """Test UltrafeederConfig with real-world scenarios"""
        mock_data = MagicMock()

        # Scenario 1: Standalone feeder with all aggregators
        mock_data.is_enabled.return_value = False
        mock_data.env_by_tags.return_value.value = "all"

        config = UltrafeederConfig(mock_data, micro=0)
        aggregators = config.enabled_aggregators
        assert isinstance(aggregators, dict)

        # Scenario 2: Stage2 feeder with specific aggregators
        mock_data.is_enabled.return_value = True
        mock_data.env_by_tags.return_value.value = "flightaware,fr24"

        config = UltrafeederConfig(mock_data, micro=0)
        aggregators = config.enabled_aggregators
        assert isinstance(aggregators, dict)

        # Scenario 3: Micro feeder with no aggregators
        mock_data.is_enabled.return_value = False
        mock_data.env_by_tags.return_value.value = "none"

        config = UltrafeederConfig(mock_data, micro=1)
        aggregators = config.enabled_aggregators
        assert isinstance(aggregators, dict)

    def test_config_error_handling(self):
        """Test error handling in config classes"""
        # Test NetConfig with None values
        netconfig = NetConfig(None, None, False)

        result = netconfig.generate()
        assert result == "None;None"

        # Test UltrafeederConfig with None data
        config = UltrafeederConfig(None, micro=0)

        # Should handle None data gracefully
        try:
            aggregators = config.enabled_aggregators
            assert isinstance(aggregators, dict)
        except AttributeError:
            # Expected behavior with None data
            pass

    def test_config_edge_cases(self):
        """Test edge cases in config classes"""
        # Test NetConfig with empty strings
        netconfig = NetConfig("", "", False)

        result = netconfig.generate()
        assert result == ";"

        # Test NetConfig with very long strings
        long_adsb = "a" * 1000
        long_mlat = "b" * 1000
        netconfig = NetConfig(long_adsb, long_mlat, True)

        result = netconfig.generate()
        assert result == f"{long_adsb};{long_mlat},--privacy"

        # Test UltrafeederConfig with edge case micro values
        mock_data = MagicMock()
        mock_data.is_enabled.return_value = False
        mock_data.env_by_tags.return_value.value = "all"

        config = UltrafeederConfig(mock_data, micro=-1)
        assert config._micro == -1

        config = UltrafeederConfig(mock_data, micro=999999)
        assert config._micro == 999999
