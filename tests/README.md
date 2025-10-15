# ADS-B Setup Test Suite

This directory contains a comprehensive test suite for the adsb-setup application. The test suite is designed to ensure the reliability and functionality of the ADS-B feeder setup system.

## Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Pytest configuration and fixtures
├── requirements.txt            # Test dependencies
├── run_tests.py               # Test runner script
├── README.md                  # This file
├── unit/                      # Unit tests
│   ├── __init__.py
│   ├── test_app.py           # Main Flask application tests
│   ├── test_util.py          # Utility functions tests
│   ├── test_config.py        # Configuration management tests
│   ├── test_data.py          # Data management tests
│   ├── test_environment.py   # Environment variable tests
│   ├── test_flask.py         # Flask utilities tests
│   ├── test_aggregators.py   # Aggregator classes tests
│   ├── test_wifi.py          # WiFi management tests
│   ├── test_netconfig.py     # Network configuration tests
│   └── test_sdr.py           # SDR device tests
└── integration/              # Integration tests
    ├── __init__.py
    └── test_system_integration.py  # System integration tests
```

## Test Categories

### Unit Tests
- **test_app.py**: Tests for the main Flask application including routes, handlers, and API endpoints
- **test_util.py**: Tests for utility functions like string cleanup, boolean conversion, and shell operations
- **test_config.py**: Tests for configuration file management and environment variable handling
- **test_data.py**: Tests for the Data singleton class and its methods
- **test_environment.py**: Tests for the Env class and environment variable management
- **test_flask.py**: Tests for Flask utilities including route management and decorators
- **test_aggregators.py**: Tests for aggregator classes (FlightAware, FlightRadar24, etc.)
- **test_wifi.py**: Tests for WiFi management and network operations
- **test_netconfig.py**: Tests for network configuration classes
- **test_sdr.py**: Tests for SDR device detection and configuration

### Integration Tests
- **test_system_integration.py**: Tests for complete system integration including configuration persistence, Flask app lifecycle, and component interaction

## Running Tests

### Prerequisites

1. Install test dependencies:
```bash
pip install -r tests/requirements.txt
```

2. Ensure you have the required system dependencies (if running integration tests):
- Docker (for container-related tests)
- Network access (for WiFi tests)
- SDR hardware (for SDR tests)

### Running Tests

#### Using the Test Runner Script
```bash
# Run all tests
python tests/run_tests.py

# Run unit tests only
python tests/run_tests.py --unit

# Run integration tests only
python tests/run_tests.py --integration

# Run with coverage
python tests/run_tests.py --coverage

# Run with verbose output
python tests/run_tests.py --verbose

# Run tests in parallel
python tests/run_tests.py --parallel 4

# Run specific test markers
python tests/run_tests.py --markers "not slow"

# Run linting checks
python tests/run_tests.py --lint

# Run security checks
python tests/run_tests.py --security

# Run all checks
python tests/run_tests.py --all
```

#### Using pytest directly
```bash
# Run all tests
pytest tests/

# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run with coverage
pytest tests/ --cov=src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup --cov-report=html

# Run specific test file
pytest tests/unit/test_app.py

# Run specific test class
pytest tests/unit/test_app.py::TestAdsbImInitialization

# Run specific test method
pytest tests/unit/test_app.py::TestAdsbImInitialization::test_adsb_im_initialization
```

## Test Markers

The test suite uses pytest markers to categorize tests:

- `unit`: Unit tests
- `integration`: Integration tests
- `slow`: Slow running tests
- `network`: Tests requiring network access
- `system`: Tests requiring system access
- `sdr`: Tests requiring SDR hardware
- `wifi`: Tests requiring WiFi access
- `docker`: Tests requiring Docker

## Test Fixtures

The test suite includes comprehensive fixtures in `conftest.py`:

- `mock_system_paths`: Mocks system paths and files
- `temp_config_dir`: Creates temporary configuration directories
- `mock_flask_app`: Mocks Flask application
- `mock_requests`: Mocks HTTP requests
- `mock_subprocess`: Mocks subprocess calls
- `mock_file_operations`: Mocks file operations
- `test_env_vars`: Sets up test environment variables

## Coverage

The test suite aims for comprehensive coverage of:
- All utility functions and classes
- Flask application routes and handlers
- Configuration management
- Data handling and persistence
- Network and WiFi operations
- SDR device management
- Aggregator functionality
- System integration

## Continuous Integration

The test suite is integrated with GitHub Actions and runs automatically on:
- Push to main, beta, or dev branches
- Pull requests to main or beta branches

The CI pipeline includes:
- Unit and integration tests across Python 3.9-3.12
- Code coverage reporting
- Linting with flake8, black, and isort
- Security scanning with bandit and safety
- Performance testing

## Mocking Strategy

The test suite uses extensive mocking to:
- Isolate units under test
- Avoid external dependencies
- Ensure tests run quickly and reliably
- Test error conditions and edge cases

Key mocking areas:
- File system operations
- Network requests
- Subprocess calls
- System configuration
- Hardware devices

## Test Data

Tests use synthetic data and mock responses to avoid:
- External API dependencies
- Real hardware requirements
- Network connectivity issues
- File system pollution

## Contributing

When adding new tests:

1. Follow the existing naming conventions
2. Use appropriate test markers
3. Include comprehensive docstrings
4. Mock external dependencies
5. Test both success and failure cases
6. Include edge cases and error conditions
7. Update this README if adding new test categories

## Troubleshooting

### Common Issues

1. **Import errors**: Ensure the adsb-setup directory is in the Python path
2. **Mock failures**: Check that mocks are properly configured in conftest.py
3. **Permission errors**: Ensure test files have proper permissions
4. **Network timeouts**: Use appropriate timeouts for network-related tests

### Debug Mode

Run tests with debug output:
```bash
pytest tests/ -v -s --tb=long
```

### Test Isolation

Each test should be independent and not rely on state from other tests. Use fixtures to set up clean test environments.

## Performance

The test suite is optimized for speed:
- Extensive use of mocking to avoid I/O operations
- Parallel test execution support
- Minimal external dependencies
- Fast test discovery and execution

## Security

The test suite includes security-focused tests:
- Input validation
- Error handling
- Configuration security
- Network security
- File system security

## Future Enhancements

Planned improvements:
- Property-based testing with Hypothesis
- Performance benchmarking
- Load testing for Flask application
- End-to-end testing with real hardware
- Visual regression testing for web interface
