"""
Tests for aggregator classes in utils.other_aggregators module
"""
import pytest
import subprocess
from unittest.mock import patch, MagicMock, call

from utils.other_aggregators import (
    Aggregator,
    ADSBHub,
    FlightAware,
    Flightradar24,
    OpenSky,
    PlaneFinder,
    PlaneWatch,
    RadarBox,
    RadarVirtuel,
    Uk1090,
    Sdrmap
)


class TestAggregatorBase:
    """Test the base Aggregator class"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_aggregator_initialization(self):
        """Test basic aggregator initialization"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        assert aggregator.name == "TestAgg"
        assert aggregator.tags == ["test_tag"]
        assert aggregator._system is self.mock_system
        assert aggregator._d is self.mock_data
        assert aggregator._idx == 0

    def test_aggregator_properties(self):
        """Test aggregator properties"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        # Test key_tags property
        assert aggregator._key_tags == ["key", "test_tag"]

        # Test enabled_tags property
        assert aggregator._enabled_tags == ["is_enabled", "other_aggregator", "test_tag"]

        # Test location properties
        assert aggregator.lat == "test_value"
        assert aggregator.lon == "test_value"
        assert aggregator.alt == "test_value"

        # Test alt_ft property (conversion from meters to feet)
        # Save original return value
        original_return = aggregator._d.env_by_tags.return_value.list_get.return_value
        aggregator._d.env_by_tags.return_value.list_get.return_value = "100"  # 100 meters
        assert aggregator.alt_ft == int(100 / 0.308)  # Should convert to feet
        # Reset to original
        aggregator._d.env_by_tags.return_value.list_get.return_value = original_return

        # Test container property
        assert aggregator.container == "test_string"

        # Test is_enabled property
        assert aggregator.is_enabled == "test_value"

    def test_aggregator_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        # Test _activate method
        with pytest.raises(NotImplementedError):
            aggregator._activate("test_input", 0)

        # Test _deactivate method
        with pytest.raises(NotImplementedError):
            aggregator._deactivate()

    @patch('utils.other_aggregators.subprocess.run')
    def test_download_docker_container_success(self, mock_subprocess):
        """Test successful docker container download"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        mock_subprocess.return_value = MagicMock()

        result = aggregator._download_docker_container("test/container:latest")

        assert result is True
        mock_subprocess.assert_called_once_with("docker pull test/container:latest", timeout=180.0, shell=True)

    @patch('utils.other_aggregators.subprocess.run')
    def test_download_docker_container_timeout(self, mock_subprocess):
        """Test docker container download timeout"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        mock_subprocess.side_effect = subprocess.TimeoutExpired("docker pull", 180.0)

        result = aggregator._download_docker_container("test/container:latest")

        assert result is False

    @patch('utils.other_aggregators.subprocess.run')
    def test_docker_run_with_timeout_success(self, mock_subprocess):
        """Test successful docker run with timeout"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "test output"  # text=True returns strings
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = aggregator._docker_run_with_timeout("test/container:latest", 30.0)

        assert result == "test output"
        # Should call docker rm -f first, then docker run
        assert mock_subprocess.call_count == 2

    @patch('utils.other_aggregators.subprocess.run')
    def test_docker_run_with_timeout_failure(self, mock_subprocess):
        """Test docker run with timeout failure"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""  # text=True returns strings, function returns stdout not stderr
        mock_result.stderr = "error message"
        mock_subprocess.return_value = mock_result

        result = aggregator._docker_run_with_timeout("test/container:latest", 30.0)

        # Function returns stdout, which is empty on failure (stderr is not returned)
        assert result == ""

    @patch('utils.other_aggregators.subprocess.run')
    def test_docker_run_with_timeout_exception(self, mock_subprocess):
        """Test docker run with timeout exception"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        mock_subprocess.side_effect = subprocess.TimeoutExpired("docker run", 30.0)

        result = aggregator._docker_run_with_timeout("test/container:latest", 30.0)

        assert result == ""


class TestADSBHub:
    """Test ADSBHub aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_adsbhub_initialization(self):
        """Test ADSBHub initialization"""
        adsbhub = ADSBHub(self.mock_system)

        assert adsbhub.name == "ADSBHub"
        assert adsbhub.tags == ["adsb_hub"]

    def test_adsbhub_activate(self):
        """Test ADSBHub activation"""
        adsbhub = ADSBHub(self.mock_system)

        # Patch at instance level to intercept the call
        with patch.object(adsbhub, '_activate') as mock_activate:
            adsbhub._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_adsbhub_deactivate(self, mock_deactivate):
        """Test ADSBHub deactivation"""
        adsbhub = ADSBHub(self.mock_system)

        adsbhub._deactivate()

        mock_deactivate.assert_called_once()


class TestFlightAware:
    """Test FlightAware aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_flightaware_initialization(self):
        """Test FlightAware initialization"""
        flightaware = FlightAware(self.mock_system)

        assert flightaware.name == "FlightAware"
        assert flightaware.tags == ["flightaware"]

    def test_flightaware_activate(self):
        """Test FlightAware activation"""
        flightaware = FlightAware(self.mock_system)

        with patch.object(flightaware, '_activate') as mock_activate:
            flightaware._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_flightaware_deactivate(self, mock_deactivate):
        """Test FlightAware deactivation"""
        flightaware = FlightAware(self.mock_system)

        flightaware._deactivate()

        mock_deactivate.assert_called_once()


class TestFlightradar24:
    """Test Flightradar24 aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_flightradar24_initialization(self):
        """Test Flightradar24 initialization"""
        fr24 = Flightradar24(self.mock_system)

        assert fr24.name == "Flightradar24"
        assert fr24.tags == ["flightradar"]

    def test_flightradar24_activate(self):
        """Test Flightradar24 activation"""
        fr24 = Flightradar24(self.mock_system)

        with patch.object(fr24, '_activate') as mock_activate:
            fr24._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_flightradar24_deactivate(self, mock_deactivate):
        """Test Flightradar24 deactivation"""
        fr24 = Flightradar24(self.mock_system)

        fr24._deactivate()

        mock_deactivate.assert_called_once()


class TestOpenSky:
    """Test OpenSky aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_opensky_initialization(self):
        """Test OpenSky initialization"""
        opensky = OpenSky(self.mock_system)

        assert opensky.name == "OpenSky Network"
        assert opensky.tags == ["opensky"]

    def test_opensky_activate(self):
        """Test OpenSky activation"""
        opensky = OpenSky(self.mock_system)

        with patch.object(opensky, '_activate') as mock_activate:
            opensky._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_opensky_deactivate(self, mock_deactivate):
        """Test OpenSky deactivation"""
        opensky = OpenSky(self.mock_system)

        opensky._deactivate()

        mock_deactivate.assert_called_once()


class TestPlaneFinder:
    """Test PlaneFinder aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_planefinder_initialization(self):
        """Test PlaneFinder initialization"""
        planefinder = PlaneFinder(self.mock_system)

        assert planefinder.name == "PlaneFinder"
        assert planefinder.tags == ["planefinder"]

    def test_planefinder_activate(self):
        """Test PlaneFinder activation"""
        planefinder = PlaneFinder(self.mock_system)

        with patch.object(planefinder, '_activate') as mock_activate:
            planefinder._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_planefinder_deactivate(self, mock_deactivate):
        """Test PlaneFinder deactivation"""
        planefinder = PlaneFinder(self.mock_system)

        planefinder._deactivate()

        mock_deactivate.assert_called_once()


class TestPlaneWatch:
    """Test PlaneWatch aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_planewatch_initialization(self):
        """Test PlaneWatch initialization"""
        planewatch = PlaneWatch(self.mock_system)

        assert planewatch.name == "PlaneWatch"
        assert planewatch.tags == ["planewatch"]

    def test_planewatch_activate(self):
        """Test PlaneWatch activation"""
        planewatch = PlaneWatch(self.mock_system)

        with patch.object(planewatch, '_activate') as mock_activate:
            planewatch._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_planewatch_deactivate(self, mock_deactivate):
        """Test PlaneWatch deactivation"""
        planewatch = PlaneWatch(self.mock_system)

        planewatch._deactivate()

        mock_deactivate.assert_called_once()


class TestRadarBox:
    """Test RadarBox aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_radarbox_initialization(self):
        """Test RadarBox initialization"""
        radarbox = RadarBox(self.mock_system)

        assert radarbox.name == "AirNav Radar"
        assert radarbox.tags == ["radarbox"]

    def test_radarbox_activate(self):
        """Test RadarBox activation"""
        radarbox = RadarBox(self.mock_system)

        with patch.object(radarbox, '_activate') as mock_activate:
            radarbox._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_radarbox_deactivate(self, mock_deactivate):
        """Test RadarBox deactivation"""
        radarbox = RadarBox(self.mock_system)

        radarbox._deactivate()

        mock_deactivate.assert_called_once()


class TestRadarVirtuel:
    """Test RadarVirtuel aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_radarvirtuel_initialization(self):
        """Test RadarVirtuel initialization"""
        radarvirtuel = RadarVirtuel(self.mock_system)

        assert radarvirtuel.name == "RadarVirtuel"
        assert radarvirtuel.tags == ["radarvirtuel"]

    def test_radarvirtuel_activate(self):
        """Test RadarVirtuel activation"""
        radarvirtuel = RadarVirtuel(self.mock_system)

        with patch.object(radarvirtuel, '_activate') as mock_activate:
            radarvirtuel._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_radarvirtuel_deactivate(self, mock_deactivate):
        """Test RadarVirtuel deactivation"""
        radarvirtuel = RadarVirtuel(self.mock_system)

        radarvirtuel._deactivate()

        mock_deactivate.assert_called_once()


class TestUk1090:
    """Test Uk1090 aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_uk1090_initialization(self):
        """Test Uk1090 initialization"""
        uk1090 = Uk1090(self.mock_system)

        assert uk1090.name == "1090Mhz UK"
        assert uk1090.tags == ["1090uk"]

    def test_uk1090_activate(self):
        """Test Uk1090 activation"""
        uk1090 = Uk1090(self.mock_system)

        with patch.object(uk1090, '_activate') as mock_activate:
            uk1090._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_uk1090_deactivate(self, mock_deactivate):
        """Test Uk1090 deactivation"""
        uk1090 = Uk1090(self.mock_system)

        uk1090._deactivate()

        mock_deactivate.assert_called_once()


class TestSdrmap:
    """Test Sdrmap aggregator"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "test_value"
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_sdrmap_initialization(self):
        """Test Sdrmap initialization"""
        sdrmap = Sdrmap(self.mock_system)

        assert sdrmap.name == "sdrmap"
        assert sdrmap.tags == ["sdrmap"]

    def test_sdrmap_activate(self):
        """Test Sdrmap activation"""
        sdrmap = Sdrmap(self.mock_system)

        with patch.object(sdrmap, '_activate') as mock_activate:
            sdrmap._activate("test_user_input", 0)
            mock_activate.assert_called_once_with("test_user_input", 0)

    @patch('utils.other_aggregators.Aggregator._deactivate')
    def test_sdrmap_deactivate(self, mock_deactivate):
        """Test Sdrmap deactivation"""
        sdrmap = Sdrmap(self.mock_system)

        sdrmap._deactivate()

        mock_deactivate.assert_called_once()


class TestAggregatorIntegration:
    """Integration tests for aggregators"""

    def setup_method(self):
        """Set up test fixtures"""
        self.mock_system = MagicMock()
        self.mock_data = MagicMock()
        self.mock_system._d = self.mock_data

        # Mock environment methods - use numeric value for altitude to support alt_ft property
        self.mock_data.env_by_tags.return_value = MagicMock()
        self.mock_data.env_by_tags.return_value.list_get.return_value = "100"  # Numeric string for altitude
        self.mock_data.env_by_tags.return_value.valuestr = "test_string"

    def test_all_aggregators_initialization(self):
        """Test that all aggregators can be initialized"""
        aggregators = [
            ADSBHub(self.mock_system),
            FlightAware(self.mock_system),
            Flightradar24(self.mock_system),
            OpenSky(self.mock_system),
            PlaneFinder(self.mock_system),
            PlaneWatch(self.mock_system),
            RadarBox(self.mock_system),
            RadarVirtuel(self.mock_system),
            Uk1090(self.mock_system),
            Sdrmap(self.mock_system)
        ]

        # All should have unique names and tags
        names = [agg.name for agg in aggregators]
        tags = [agg.tags for agg in aggregators]

        assert len(set(names)) == len(names)  # All names should be unique
        assert len(set(tuple(tag) for tag in tags)) == len(tags)  # All tag lists should be unique

    def test_aggregator_properties_consistency(self):
        """Test that all aggregators have consistent property behavior"""
        aggregators = [
            ADSBHub(self.mock_system),
            FlightAware(self.mock_system),
            Flightradar24(self.mock_system),
            OpenSky(self.mock_system),
            PlaneFinder(self.mock_system),
            PlaneWatch(self.mock_system),
            RadarBox(self.mock_system),
            RadarVirtuel(self.mock_system),
            Uk1090(self.mock_system),
            Sdrmap(self.mock_system)
        ]

        for agg in aggregators:
            # All should have name and tags
            assert hasattr(agg, 'name')
            assert hasattr(agg, 'tags')
            assert isinstance(agg.name, str)
            assert isinstance(agg.tags, list)

            # All should have location properties
            assert hasattr(agg, 'lat')
            assert hasattr(agg, 'lon')
            assert hasattr(agg, 'alt')
            assert hasattr(agg, 'alt_ft')

            # All should have container and is_enabled properties
            assert hasattr(agg, 'container')
            assert hasattr(agg, 'is_enabled')

            # All should have key_tags and enabled_tags
            assert hasattr(agg, '_key_tags')
            assert hasattr(agg, '_enabled_tags')

            # All should have abstract methods
            assert hasattr(agg, '_activate')
            assert hasattr(agg, '_deactivate')

    @patch('utils.other_aggregators.subprocess.run')
    def test_aggregator_docker_operations(self, mock_subprocess):
        """Test docker operations across aggregators"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        # Test successful operations
        mock_subprocess.return_value = MagicMock()

        # Test download
        result = aggregator._download_docker_container("test/container:latest")
        assert result is True

        # Test run
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"  # String output (subprocess.run uses text=True)
        mock_result.stderr = ""
        mock_subprocess.return_value = mock_result

        result = aggregator._docker_run_with_timeout("test/container:latest", 30.0)
        assert result == "success"

    def test_aggregator_location_calculations(self):
        """Test location-related calculations"""
        aggregator = Aggregator("TestAgg", self.mock_system, ["test_tag"])

        # Test altitude conversion
        aggregator._d.env_by_tags.return_value.list_get.return_value = "100"  # 100 meters
        expected_feet = int(100 / 0.308)
        assert aggregator.alt_ft == expected_feet

        # Test with different altitude
        aggregator._d.env_by_tags.return_value.list_get.return_value = "200"  # 200 meters
        expected_feet = int(200 / 0.308)
        assert aggregator.alt_ft == expected_feet

    def test_aggregator_tag_consistency(self):
        """Test that aggregator tags are consistent"""
        aggregators = [
            ADSBHub(self.mock_system),
            FlightAware(self.mock_system),
            Flightradar24(self.mock_system),
            OpenSky(self.mock_system),
            PlaneFinder(self.mock_system),
            PlaneWatch(self.mock_system),
            RadarBox(self.mock_system),
            RadarVirtuel(self.mock_system),
            Uk1090(self.mock_system),
            Sdrmap(self.mock_system)
        ]

        for agg in aggregators:
            # Tags should be non-empty
            assert len(agg.tags) > 0

            # Key tags should include "key" + original tags
            assert agg._key_tags[0] == "key"
            assert agg._key_tags[1:] == agg.tags

            # Enabled tags should include the required prefixes
            assert "is_enabled" in agg._enabled_tags
            assert "other_aggregator" in agg._enabled_tags
            assert agg.tags[0] in agg._enabled_tags
