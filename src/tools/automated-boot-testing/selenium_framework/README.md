# Selenium Test Framework

A maintainable, browser-agnostic selenium testing framework using the Page Object Model pattern.

## Architecture

### Page Object Model (POM)

The framework separates UI locators and interactions from test logic:

- **Pages** (`pages/`): Define page structure and element locators
- **Base Page** (`base_page.py`): Common WebDriver operations
- **Test Runner** (`test_runner.py`): Orchestrates test workflow
- **Browser Factory** (`browser_factory.py`): Creates browser instances

### Key Components

```
selenium_framework/
├── config.py              # Configuration and timeout constants
├── exceptions.py          # Custom exception hierarchy
├── browser_factory.py     # Browser creation (Chrome, Firefox)
├── base_page.py          # Base page with common operations
├── test_runner.py        # Test orchestration
└── pages/
    ├── basic_setup_page.py    # Basic setup form
    ├── sdr_setup_page.py      # SDR configuration
    ├── feeder_homepage.py     # Homepage verification
    └── waiting_page.py        # Page transition handling
```

## Usage

### Running Tests

```bash
# Run with Chrome (default)
python3 run_selenium_test.py 192.168.1.100

# Run with Firefox
python3 run_selenium_test.py 192.168.1.100 --browser firefox

# Run with visible browser (no headless)
python3 run_selenium_test.py 192.168.1.100 --no-headless

# With debug logging
python3 run_selenium_test.py 192.168.1.100 --log-level DEBUG
```

### Programmatic Usage

```python
from selenium_framework.config import TestConfig
from selenium_framework.test_runner import SeleniumTestRunner

config = TestConfig(rpi_ip="192.168.1.100", browser="chrome")

with SeleniumTestRunner(config) as runner:
    success = runner.run_basic_setup_test()
```

## Adding New Tests

### 1. Create a Page Object

```python
# pages/new_page.py
from selenium.webdriver.common.by import By
from ..base_page import BasePage

class NewPage(BasePage):
    # Define locators
    SOME_BUTTON = (By.ID, "button_id")

    def do_action(self):
        self.click_element(self.SOME_BUTTON)
```

### 2. Add Test Logic to Runner

```python
# In test_runner.py
def run_new_test(self):
    new_page = NewPage(self.driver, self.config.base_url)
    new_page.navigate()
    new_page.do_action()
```

### 3. Write Unit Tests

```python
# tests/test_new_page.py
def test_new_page_action(mock_driver):
    page = NewPage(mock_driver, "http://test.com")
    page.do_action()
    # Assertions...
```

## Design Principles

### Single Responsibility

Each class has one job:
- **Pages**: Know page structure
- **Test Runner**: Orchestrate workflow
- **Browser Factory**: Create browsers
- **Config**: Hold settings

### DRY (Don't Repeat Yourself)

Common operations in `BasePage`:
- `click_element()` - Handles regular and JS clicks
- `find_element()` - Unified element finding
- `enter_text()` - Text input with optional clear

### Browser Agnostic

Switch browsers with one argument:
```bash
--browser chrome  # or firefox
```

Both use same page objects and test logic.

## Configuration

### Test Settings

Modify `config.py` to change defaults:

```python
@dataclass
class TestConfig:
    rpi_ip: str
    browser: Literal["chrome", "firefox"] = "chrome"
    headless: bool = True
    timeout: int = 90
    # ... more settings
```

### Timeouts

Adjust timeouts in `config.py`:

```python
class Timeouts:
    PAGE_LOAD = 30
    SHORT_WAIT = 5
    MEDIUM_WAIT = 30
    LONG_WAIT = 600
    # ...
```

## Testing

Run unit tests:

```bash
# All tests
uv run pytest src/tools/automated-boot-testing/tests/ -v

# Specific test file
uv run pytest src/tools/automated-boot-testing/tests/test_config.py -v

# With coverage
uv run pytest src/tools/automated-boot-testing/tests/ --cov=selenium_framework
```

## Troubleshooting

### Element Not Found

1. Check locator in page object
2. Increase timeout for slow pages
3. Add explicit wait in page method

### Click Not Working

The framework automatically falls back to JavaScript click if regular click fails.

### Browser Setup Fails

**On x86_64:**
- Ensure Chrome/Firefox is installed on system
- Check network connectivity (Selenium Manager downloads drivers automatically)

**On ARM64:**
- Install chromium and chromium-driver: `sudo apt install chromium chromium-driver`
- For Firefox, install geckodriver manually (see main README for instructions)
- Ensure browsers are in PATH

## Dependencies

- `selenium>=4.0.0` - WebDriver automation (includes Selenium Manager)
- `pytest>=8.0.0` - Testing framework (for running tests)
- `pytest-mock` - Mocking support (for unit tests)
