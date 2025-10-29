# ADS-B Setup Test Suite

**Last Updated:** 2025-10-28
**Test Suite Status:** 371 passing tests, 33% coverage

This directory contains a comprehensive test suite for the adsb-setup application. The test suite is designed to ensure the reliability and functionality of the ADS-B feeder setup system.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Test Structure](#test-structure)
3. [Running Tests](#running-tests)
4. [Writing Tests](#writing-tests)
5. [Test Patterns & Best Practices](#test-patterns--best-practices)
6. [Common Pitfalls](#common-pitfalls)
7. [Test Fixtures](#test-fixtures)
8. [Coverage Analysis](#coverage-analysis)
9. [Test Markers](#test-markers)
11. [Known Issues](#known-issues)
12. [Contributing](#contributing)
13. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Install dependencies
uv pip install pytest pytest-cov pytest-mock

# Run all tests (using Makefile - recommended)
make run-tests

# Or run tests directly with pytest
uv run pytest tests/

# Run only unit tests
uv run pytest tests/unit/

# Run with coverage
uv run pytest --cov=src --cov-report=term-missing tests/

# Run specific test file
uv run pytest tests/unit/test_system.py -v
```

---

## Test Structure

### Directory Organization

```
tests/
├── README.md                          # This file
├── TEST_STATUS.md                     # Current status & planned improvements
├── conftest.py                        # Shared fixtures and configuration
├── requirements.txt                   # Test dependencies
├── run_tests.py                       # Test runner script
├── test_fixture_setup.py              # Tests for the adsb_test_env fixture
└── unit/                              # Unit tests
    ├── test_aggregators.py            # Aggregator module tests
    ├── test_app.py                    # Flask application tests
    ├── test_config.py                 # Configuration module tests
    ├── test_data.py                   # Data class tests
    ├── test_environment.py            # Environment variable tests
    ├── test_flask.py                  # Flask utilities tests
    ├── test_netconfig.py              # Network configuration tests
    ├── test_paths.py                  # Path configuration tests
    ├── test_sdr.py                    # SDR module tests
    ├── test_system.py                 # System operations tests
    ├── test_util.py                   # Utility functions tests
    └── test_wifi.py                   # WiFi module tests

Note: The integration/ directory exists but currently has no tests. Integration tests
were removed in favor of comprehensive unit tests with proper mocking.
```

### Test Organization by Module

| Module | Coverage | Tests | Status |
|--------|----------|-------|--------|
| **system.py** | 95% | 54 | ✅ Excellent |
| **paths.py** | 99% | 8 | ✅ Excellent |
| **flask.py** | 100% | 20 | ✅ Complete |
| **config.py** | 81% | 19 | ✅ Good |
| **wifi.py** | 81% | 26 | ✅ Good |
| **util.py** | 78% | 43 | ✅ Good |
| **sdr.py** | 67% | 30 | ⚠️ Needs improvement |
| **environment.py** | 58% | 41 | ⚠️ Needs improvement |
| **data.py** | 53% | 20 | ⚠️ Needs improvement |
| **other_aggregators.py** | 39% | 43 | ⚠️ Needs improvement |
| **netconfig.py** | 29% | 28 | ❌ Needs work |
| **background.py** | 29% | 0 | ❌ No tests |
| **agg_status.py** | 22% | 0 | ❌ No tests |
| **app.py** | 24% | 51 | ❌ Large surface area |

---

## Running Tests

### Basic Test Commands

```bash
# Run all tests with verbose output
uv run pytest tests/ -v

# Run specific test class
uv run pytest tests/unit/test_system.py::TestLock -v

# Run specific test
uv run pytest tests/unit/test_system.py::TestLock::test_lock_initialization -v

# Show detailed failure information
uv run pytest tests/ -vv --tb=short

# Stop at first failure
uv run pytest tests/ -x
```

### Using the Test Runner Script

```bash
# Run all tests
python3 tests/run_tests.py

# Run unit tests only
python3 tests/run_tests.py --unit

# Run with coverage
python3 tests/run_tests.py --coverage

# Run with verbose output
python3 tests/run_tests.py --verbose

# Run tests in parallel
python3 tests/run_tests.py --parallel 4

# Run specific test markers
python3 tests/run_tests.py --markers "not slow"

# Run linting checks
python3 tests/run_tests.py --lint

# Run security checks
python3 tests/run_tests.py --security

# Run all checks
python3 tests/run_tests.py --all

# Note: --integration option exists but currently runs no tests
```

### Coverage Commands

```bash
# Run with coverage report
uv run pytest --cov=src --cov-report=term-missing tests/

# Generate HTML coverage report
uv run pytest --cov=src --cov-report=html tests/
# Open coverage_html_report/index.html in browser

# Check coverage for specific module
uv run pytest --cov=src --cov-report=term-missing tests/unit/test_system.py
```

### Filtering Tests

```bash
# Run only tests matching a pattern
uv run pytest tests/ -k "test_lock"

# Run tests with specific markers (if configured)
uv run pytest tests/ -m "unit"

# Run tests in parallel (if pytest-xdist installed)
uv run pytest tests/ -n auto
```

---

## Writing Tests

### Basic Test Template

```python
"""
Tests for utils.module_name module
"""
import pytest
from unittest.mock import patch, MagicMock

from utils.module_name import FunctionOrClass


class TestFunctionOrClass:
    """Test the FunctionOrClass"""

    def test_basic_functionality(self, adsb_test_env):
        """Test basic functionality"""
        # Arrange
        expected_result = "expected"

        # Act
        result = FunctionOrClass()

        # Assert
        assert result == expected_result
```

### Test Organization

All tests are currently unit tests located in `tests/unit/`:

- **test_app.py**: Flask application routes, handlers, and API endpoints
- **test_util.py**: Utility functions like string cleanup, boolean conversion
- **test_config.py**: Configuration file management and environment variables
- **test_data.py**: Data singleton class and its methods
- **test_environment.py**: Env class and environment variable management
- **test_flask.py**: Flask utilities including route management and decorators
- **test_aggregators.py**: Aggregator classes (FlightAware, Flightradar24, etc.)
- **test_wifi.py**: WiFi management and network operations
- **test_netconfig.py**: Network configuration classes
- **test_sdr.py**: SDR device detection and configuration
- **test_system.py**: System operations (shutdown, Docker, network, locks)

---

## Test Patterns & Best Practices

### 1. Module Reloading Pattern

**Problem:** Python caches module imports. Tests that modify `ADSB_BASE_DIR` can affect other tests.

**Solution:** Reload modules after changing paths

```python
import importlib
import os
from pathlib import Path
from unittest.mock import patch

def test_with_custom_base_dir(self):
    """Test with custom base directory"""
    test_dir = "/tmp/my-test-dir"

    with patch.dict(os.environ, {'ADSB_BASE_DIR': test_dir}):
        # Reload modules to pick up new ADSB_BASE_DIR
        import utils.paths
        import utils.config
        import utils.util

        importlib.reload(utils.paths)
        importlib.reload(utils.config)
        importlib.reload(utils.util)

        # Run test assertions
        assert utils.paths.ADSB_BASE_DIR == Path(test_dir)

    # CRITICAL: Restore to session state after test
    import utils.paths
    import utils.config
    import utils.util

    importlib.reload(utils.paths)
    importlib.reload(utils.config)
    importlib.reload(utils.util)
```

**Files that need this pattern:**
- `test_paths.py` - When testing path configuration
- Any test that uses `patch.dict(os.environ, {'ADSB_BASE_DIR': ...})`

### 2. Config Isolation Pattern

**Problem:** `Env` class reads from `config.json` on initialization. Previous test values can pollute later tests.

**Solution:** Clear config before creating `Env` objects

```python
from utils.config import write_values_to_config_json
from utils.environment import Env

def test_env_properties(self, adsb_test_env):
    """Test Env properties"""
    # CRITICAL: Clear config to avoid interference from previous tests
    write_values_to_config_json({}, reason="test_env_properties")

    # Now create Env - it will get clean state
    env = Env("TEST_VAR", value="test_value", is_mandatory=True)

    assert env.value == "test_value"
```

**When to use:**
- ✅ Any test creating `Env` objects
- ✅ Tests in `test_environment.py`
- ✅ Tests that check specific config values

### 3. Mocking System Calls

**Problem:** Tests shouldn't make real system calls (subprocess, network, file operations outside test dir).

**Solution:** Use proper mock patch paths

```python
from unittest.mock import patch, MagicMock

@patch('utils.system.run_shell_captured')  # Patch where it's IMPORTED, not where it's defined
def test_docker_operation(self, mock_run_shell):
    """Test Docker operation"""
    mock_run_shell.return_value = (True, "ultrafeeder;Up 2 hours")

    from utils.system import System
    system = System(MagicMock())

    status = system.getContainerStatus("ultrafeeder")
    assert status == "up"
```

**Common mock paths:**
- `utils.system.run_shell_captured` (NOT `utils.util.run_shell_captured`)
- `utils.system.subprocess.run`
- `utils.system.requests.get`
- `utils.system.socket.socket`

**Why patch where it's imported?**
- ✅ `@patch('utils.system.run_shell_captured')` - Works (patches the reference in system.py)
- ❌ `@patch('utils.util.run_shell_captured')` - Doesn't work (system.py has its own reference)

### 4. Thread Safety Testing

**Pattern for testing concurrent operations:**

```python
import threading
import time

def test_concurrent_access(self):
    """Test concurrent access to shared resource"""
    lock = Lock()
    results = []

    def worker(worker_id):
        if lock.acquire(blocking=True, timeout=1.0):
            results.append(f"start-{worker_id}")
            time.sleep(0.1)
            results.append(f"end-{worker_id}")
            lock.release()

    # Start multiple threads
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Verify sequential execution
    assert len(results) == 4
    assert results[0].startswith("start")
    assert results[1].startswith("end")
```

**Use for:**
- Lock mechanisms
- Shared cache access
- Background task management

### 5. Testing Lock Objects

**Problem:** `threading.Lock()` returns a `_thread.lock` object, not `threading.Lock` instance.

**Solution:** Check for methods, not type

```python
def test_lock_initialization(self):
    """Test Lock is properly initialized"""
    lock = Lock()

    # ❌ WRONG: isinstance(lock.lock, threading.Lock)  # Fails!
    # ✅ RIGHT: Check for expected methods
    assert hasattr(lock.lock, 'acquire')
    assert hasattr(lock.lock, 'release')
    assert not lock.locked()
```

### 6. Testing Background Threads

**Pattern for testing async operations:**

```python
@patch('subprocess.run')
def test_bg_run_with_command(self, mock_subprocess):
    """Test bg_run executes command in background"""
    lock = Lock()
    restart = Restart(lock)

    result = restart.bg_run(cmdline="echo test")

    # Should return True immediately
    assert result

    # Wait for background thread to complete
    restart.wait_restart_done(timeout=2.0)

    # Verify command was executed
    mock_subprocess.assert_called_once()

    # Lock should be released
    assert not lock.locked()
```

**Key points:**
- Start operation (non-blocking)
- Wait for completion with timeout
- Verify side effects
- Check cleanup (locks released, etc.)

### 7. Testing Network Operations

**Mock network calls to avoid real network access:**

```python
@patch('requests.get')
def test_check_ip_success(self, mock_requests):
    """Test check_ip with successful API call"""
    mock_response = MagicMock()
    mock_response.text = "203.0.113.42"
    mock_response.status_code = 200
    mock_requests.return_value = mock_response

    system = System(MagicMock())
    ip, status = system.check_ip()

    assert ip == "203.0.113.42"
    assert status == 200

@patch('socket.socket')
def test_check_gpsd_success(self, mock_socket_class):
    """Test GPSD connection"""
    mock_socket = MagicMock()
    mock_socket_class.return_value = mock_socket

    system = System(MagicMock())
    result = system.check_gpsd()

    assert result is True
    mock_socket.connect.assert_called()
```

---

## Common Pitfalls

### ❌ Pitfall 1: Wrong Mock Patch Path

```python
# ❌ WRONG - Patches the original definition
@patch('utils.util.run_shell_captured')
def test_system_method(self, mock_run_shell):
    # This won't work because system.py imported run_shell_captured
    system.refreshDockerPs()

# ✅ CORRECT - Patches where it's imported
@patch('utils.system.run_shell_captured')
def test_system_method(self, mock_run_shell):
    # This works because we patch system.py's reference
    system.refreshDockerPs()
```

**Rule:** Patch where the function is IMPORTED, not where it's DEFINED.

### ❌ Pitfall 2: Not Clearing Config Between Tests

```python
# ❌ WRONG - Previous test values pollute this test
def test_env_value(self, adsb_test_env):
    env = Env("TEST_VAR", value="new_value")
    assert env.value == "new_value"  # May fail if previous test set it!

# ✅ CORRECT - Clear config first
def test_env_value(self, adsb_test_env):
    write_values_to_config_json({}, reason="test_env_value")
    env = Env("TEST_VAR", value="new_value")
    assert env.value == "new_value"  # Always works
```

### ❌ Pitfall 3: Not Restoring Module State

```python
# ❌ WRONG - Module state persists to other tests
def test_custom_paths(self):
    with patch.dict(os.environ, {'ADSB_BASE_DIR': '/tmp/test'}):
        importlib.reload(utils.paths)
        # test assertions
    # Module still has /tmp/test paths!

# ✅ CORRECT - Restore after test
def test_custom_paths(self):
    with patch.dict(os.environ, {'ADSB_BASE_DIR': '/tmp/test'}):
        importlib.reload(utils.paths)
        # test assertions

    # Restore to session fixture state
    importlib.reload(utils.paths)
    importlib.reload(utils.config)
    importlib.reload(utils.util)
```

### ❌ Pitfall 4: Forgetting exist_ok=True

```python
# ❌ WRONG - Fails if directory already exists
config_dir.mkdir(parents=True)

# ✅ CORRECT - Idempotent directory creation
config_dir.mkdir(parents=True, exist_ok=True)
```

### ❌ Pitfall 5: Testing threading.Lock Type

```python
# ❌ WRONG - Type check fails
assert isinstance(lock.lock, threading.Lock)

# ✅ CORRECT - Check for methods
assert hasattr(lock.lock, 'acquire')
assert hasattr(lock.lock, 'release')
```

### ❌ Pitfall 6: Not Using adsb_test_env Fixture

```python
# ❌ WRONG - Tests interfere with each other
def test_config_write(self):
    write_values_to_config_json({"VAR": "value"}, reason="test")
    # Writes to shared location!

# ✅ CORRECT - Use isolated test environment
def test_config_write(self, adsb_test_env):
    write_values_to_config_json({"VAR": "value"}, reason="test")
    # Writes to temporary test directory
```

### ❌ Pitfall 7: Not Waiting for Background Threads

```python
# ❌ WRONG - May check before thread completes
def test_bg_operation(self):
    restart.bg_run(cmdline="echo test")
    assert not restart.is_restarting  # May still be running!

# ✅ CORRECT - Wait for completion
def test_bg_operation(self):
    restart.bg_run(cmdline="echo test")
    restart.wait_restart_done(timeout=2.0)
    assert not restart.is_restarting
```

---

## Test Fixtures

The test suite includes comprehensive fixtures in `conftest.py`:

### The `adsb_test_env` Fixture

**Most important fixture** - Use this for almost all tests:

```python
def test_my_function(self, adsb_test_env):
    """Test my function

    Args:
        adsb_test_env: Session-scoped fixture providing isolated test environment
    """
    # This fixture provides:
    # - Temporary ADSB_BASE_DIR with proper structure
    # - Isolated config.json and .env files
    # - Essential copied files (docker.image.versions, scripts, etc.)
    # - Machine ID and version files

    from utils.config import write_values_to_config_json

    # Use the test environment
    write_values_to_config_json({"TEST_VAR": "value"}, reason="test")
```

**When to use:**
- ✅ Any test that reads/writes config files
- ✅ Any test that imports modules with path dependencies
- ✅ Any test that needs isolated file system state
- ❌ Pure unit tests with no file I/O (use mocks instead)

### Other Fixtures

- `mock_system_paths`: Mocks system paths and files
- `temp_config_dir`: Creates temporary configuration directories
- `mock_flask_app`: Mocks Flask application
- `mock_requests`: Mocks HTTP requests
- `mock_subprocess`: Mocks subprocess calls
- `mock_file_operations`: Mocks file operations
- `test_env_vars`: Sets up test environment variables

---

## Coverage Analysis

### Current Coverage Status (2025-10-23)

**Overall:** 39% coverage (5,218 statements, 3,186 uncovered)

**High Coverage Modules (Good Examples):**
- `flask.py`: 100% (35/35 statements) ✅
- `paths.py`: 99% (103/103 statements) ✅
- `system.py`: 95% (206/206 statements) ✅
- `config.py`: 81% (78/78 statements) ✅
- `wifi.py`: 81% (220/220 statements) ✅

**Low Coverage Modules (Need Tests):**
- `agg_status.py`: 22% (477 statements, 374 uncovered) ❌
- `background.py`: 29% (21 statements, 15 uncovered) ❌
- `netconfig.py`: 29% (117 statements, 83 uncovered) ❌
- `other_aggregators.py`: 39% (309 statements, 190 uncovered) ❌
- `app.py`: 24% (2,875 statements, 2,173 uncovered) ❌

### How to Improve Coverage

1. **Check current coverage:**
   ```bash
   uv run pytest --cov=src --cov-report=term-missing tests/
   ```

2. **Identify uncovered lines:**
   ```bash
   uv run pytest --cov=src --cov-report=html tests/
   # Open coverage_html_report/index.html
   ```

3. **Focus on critical modules first:**
   - Security-related: `system.py` ✅ (Done!), `agg_status.py` ❌
   - Core functionality: `app.py`, `data.py`
   - Network operations: `netconfig.py`, `other_aggregators.py`

4. **Target 75% overall coverage** as the next milestone

### Coverage Best Practices

**DO:**
- ✅ Test happy paths AND error paths
- ✅ Test edge cases (empty strings, None, large values)
- ✅ Test exception handling
- ✅ Test all branches (if/else, try/except)
- ✅ Test timeout scenarios
- ✅ Test concurrent access

**DON'T:**
- ❌ Chase 100% coverage on boilerplate code
- ❌ Write tests just to increase numbers
- ❌ Skip error paths because they're "unlikely"
- ❌ Ignore thread safety testing

---

## Test Markers

The test suite uses pytest markers to categorize tests:

- `unit`: Unit tests
- `slow`: Slow running tests
- `network`: Tests requiring network access
- `system`: Tests requiring system access
- `sdr`: Tests requiring SDR hardware
- `wifi`: Tests requiring WiFi access
- `docker`: Tests requiring Docker

---

## Continuous Integration

The test suite is integrated with GitHub Actions and runs automatically on:
- Push to main, beta, or dev branches
- Pull requests to main or beta branches

The CI pipeline includes:
- Unit tests across Python 3.9-3.12
- Code coverage reporting
- Linting with flake8, black, isort, and ruff

---

## Contributing

### Adding New Tests

1. **All new tests go in `tests/unit/`**
   - Single module/function tests with comprehensive mocking

2. **Use the template:**
   ```bash
   cp tests/unit/test_system.py tests/unit/test_mymodule.py
   # Edit to match your module
   ```

3. **Follow naming conventions:**
   - Test file: `test_modulename.py`
   - Test class: `TestClassName`
   - Test method: `test_what_it_does_under_what_condition`

4. **Add docstrings:**
   ```python
   def test_lock_concurrent_access(self):
       """Test lock prevents concurrent access"""
       # Arrange, Act, Assert
   ```

5. **Run tests before committing:**
   ```bash
   # Run your new tests
   uv run pytest tests/unit/test_mymodule.py -v

   # Check coverage
   uv run pytest --cov=src --cov-report=term-missing tests/unit/test_mymodule.py

   # Run full unit test suite
   uv run pytest tests/unit/ -v
   ```

### Test Quality Checklist

Before submitting tests, verify:

- [ ] Tests use `adsb_test_env` fixture when needed
- [ ] Mocks use correct patch paths (where imported, not defined)
- [ ] Config is cleared before Env object creation
- [ ] Modules are reloaded if paths are modified
- [ ] Background threads have wait/timeout logic
- [ ] Network calls are mocked
- [ ] Thread safety is tested for concurrent code
- [ ] Error paths are tested, not just happy paths
- [ ] Tests are independent (can run in any order)
- [ ] Tests clean up after themselves
- [ ] Docstrings explain what's being tested
- [ ] Coverage report shows new lines are tested

### Examples from test_system.py

The `test_system.py` file is an excellent reference for well-written tests. See `tests/unit/test_system.py` for examples of:

- ✅ **Comprehensive coverage** (95% of system.py)
- ✅ **Proper mocking** (subprocess, network, sockets)
- ✅ **Thread safety testing** (concurrent access, locks)
- ✅ **Security testing** (command injection, timeout handling)
- ✅ **Clear documentation** (descriptive test names, docstrings)
- ✅ **Organized structure** (6 test classes, 54 tests total)

**Study these test classes:**
1. `TestLock` - Testing thread synchronization primitives
2. `TestRestart` - Testing background operations and state management
3. `TestSystemShutdown` - Testing system commands with mocking
4. `TestSystemNetwork` - Testing network operations
5. `TestSystemDocker` - Testing Docker container management
6. `TestSystemThreadSafety` - Testing concurrent access patterns

---

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

---

## Performance

The test suite is optimized for speed:
- Extensive use of mocking to avoid I/O operations
- Parallel test execution support
- Minimal external dependencies
- Fast test discovery and execution

---

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

---

## Test Data

Tests use synthetic data and mock responses to avoid:
- External API dependencies
- Real hardware requirements
- Network connectivity issues
- File system pollution

---

## Security

The test suite includes security-focused tests:
- Input validation
- Error handling
- Configuration security
- Network security
- File system security

---

## Questions?

**For test-related questions:**
1. Check this guide first
2. Look at similar tests in `tests/unit/test_system.py`
3. Check pytest documentation: https://docs.pytest.org/
4. Check unittest.mock documentation: https://docs.python.org/3/library/unittest.mock.html

**Common resources:**
- pytest fixtures: https://docs.pytest.org/en/stable/fixture.html
- unittest.mock: https://docs.python.org/3/library/unittest.mock.html
- pytest-cov: https://pytest-cov.readthedocs.io/

**Need help?**
- Open an issue with the `testing` label
- Include: Test file, test name, error message, what you tried

---

**See [TEST_STATUS.md](TEST_STATUS.md) for current coverage metrics and planned improvements.**

**Happy Testing! 🧪**
