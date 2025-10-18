#!/usr/bin/env python3
"""
ADS-B Feeder Test Service

A systemd service that provides a web API for triggering automated tests.
Listens for POST requests to /api/trigger-boot-test with GitHub release URLs.

Features:
- Validates GitHub release URLs from dirkhh/adsb-feeder-image repo
- Queues test requests with duplicate prevention (1 hour)
- Processes queue sequentially with timeouts
- Configurable IP addresses and settings
- Comprehensive logging
"""

import argparse
import hmac
import json
import logging
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from queue import Empty, Queue
from typing import Dict, Optional
from urllib.parse import urlparse

from flask import Flask, jsonify, request


class APIKeyAuth:
    """Simple API key authentication with timing-safe comparison."""

    def __init__(self, api_keys: Dict[str, str]):
        """
        Initialize with API keys.

        Args:
            api_keys: Dict mapping API key to user identifier
                     e.g., {"abc123...": "github-ci", "def456...": "developer1"}
        """
        self.api_keys = api_keys
        if not api_keys:
            logging.warning("⚠️  No API keys configured - authentication will reject all requests")

    def validate_key(self, provided_key: str) -> Optional[str]:
        """
        Validate an API key using timing-safe comparison.

        Returns user identifier if valid, None if invalid.
        """
        if not provided_key:
            return None

        # Use timing-safe comparison to prevent timing attacks
        for valid_key, user_id in self.api_keys.items():
            if hmac.compare_digest(provided_key, valid_key):
                return user_id

        return None

    def require_auth(self, f):
        """Decorator to require API key authentication on endpoints."""

        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get API key from header
            api_key = request.headers.get("X-API-Key")

            if not api_key:
                logging.warning(f"Authentication failed: No API key provided from {request.environ.get('REMOTE_ADDR')}")
                return jsonify({"error": "Missing X-API-Key header"}), 401

            # Validate the key
            user_id = self.validate_key(api_key)
            if not user_id:
                logging.warning(f"Authentication failed: Invalid API key from {request.environ.get('REMOTE_ADDR')}")
                return jsonify({"error": "Invalid API key"}), 401

            # Log successful authentication
            logging.info(f"Authenticated request from user: {user_id}")

            # Add user_id to request context for use in endpoint
            request.user_id = user_id

            return f(*args, **kwargs)

        return decorated_function


class TestQueue:
    """Manages the test queue with duplicate prevention."""

    def __init__(self):
        self.queue = Queue()
        self.processed_urls = {}  # url -> timestamp
        self.duplicate_window = timedelta(hours=1)
        self._lock = threading.Lock()

    def add_test(self, url: str, requester_ip: str = "unknown") -> Dict[str, str]:
        """Add a test to the queue if not a duplicate."""
        with self._lock:
            now = datetime.now()
            url_key = url.lower().strip()

            # Check for recent duplicates
            if url_key in self.processed_urls:
                last_processed = self.processed_urls[url_key]
                if now - last_processed < self.duplicate_window:
                    remaining_time = self.duplicate_window - (now - last_processed)
                    return {
                        "status": "duplicate",
                        "message": f"URL was processed {remaining_time} ago. Ignoring duplicate.",
                        "queue_size": self.queue.qsize(),
                    }

            # Add to queue
            test_item = {
                "url": url,
                "requester_ip": requester_ip,
                "added_at": now.isoformat(),
                "id": f"test_{int(time.time())}_{len(url_key)}",
            }

            self.queue.put(test_item)
            self.processed_urls[url_key] = now

            return {
                "status": "queued",
                "message": f"Test queued successfully",
                "queue_size": self.queue.qsize(),
                "test_id": test_item["id"],
            }

    def get_next_test(self) -> Optional[Dict]:
        """Get the next test from the queue."""
        try:
            return self.queue.get_nowait()
        except Empty:
            return None

    def mark_completed(self, test_id: str, success: bool, message: str = ""):
        """Mark a test as completed."""
        logging.info(f"Test {test_id} completed: {'SUCCESS' if success else 'FAILED'} - {message}")


class GitHubValidator:
    """Validates GitHub release URLs."""

    def __init__(self, allowed_repo: str = "dirkhh/adsb-feeder-image"):
        self.allowed_repo = allowed_repo
        self.allowed_domains = ["github.com", "githubusercontent.com"]

    def validate_url(self, url: str) -> Dict[str, str]:
        """Validate that the URL is a GitHub release artifact from the allowed repo."""
        try:
            parsed = urlparse(url)

            # Check domain
            if parsed.netloc not in self.allowed_domains:
                return {"valid": False, "error": f"URL must be from GitHub (got {parsed.netloc})"}

            # Check if it's a release download URL
            if not self._is_release_url(url):
                return {"valid": False, "error": "URL must be a GitHub release artifact download link"}

            # Verify it's from the correct repository
            if not self._verify_repository(url):
                return {"valid": False, "error": f"URL must be from repository {self.allowed_repo}"}

            return {"valid": True, "message": "Valid GitHub release URL"}

        except Exception as e:
            return {"valid": False, "error": f"Invalid URL format: {str(e)}"}

    def _is_release_url(self, url: str) -> bool:
        """Check if URL looks like a GitHub release download."""
        # Common patterns for GitHub release downloads
        patterns = ["/releases/download/", "/archive/refs/tags/", ".img.xz", ".img.gz", ".zip", ".tar.gz"]
        return any(pattern in url for pattern in patterns)

    def _verify_repository(self, url: str) -> bool:
        """Verify the URL is from the correct repository."""
        # Extract repository from URL
        # Format: https://github.com/owner/repo/releases/download/...
        parts = url.split("/")
        if len(parts) >= 5 and parts[2] == "github.com":
            repo_part = f"{parts[3]}/{parts[4]}"
            return repo_part.lower() == self.allowed_repo.lower()
        return False


class TestExecutor:
    """Executes the actual test using the test-feeder-image.py script."""

    def __init__(self, rpi_ip: str, kasa_ip: str, timeout_minutes: int = 10):
        # Validate all inputs at initialization - fail fast if invalid
        self.rpi_ip = self._validate_ip(rpi_ip, "rpi_ip")
        self.kasa_ip = self._validate_ip(kasa_ip, "kasa_ip")
        self.timeout_minutes = self._validate_timeout(timeout_minutes)
        self.script_path = self._validate_script_path()
        self.venv_python = self._validate_python_path()

    def _validate_ip(self, ip: str, name: str) -> str:
        """Validate IP address format - simple and clear."""
        import ipaddress

        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            raise ValueError(f"Invalid {name}: '{ip}' is not a valid IP address")

    def _validate_timeout(self, timeout: int) -> int:
        """Validate timeout is reasonable."""
        if not isinstance(timeout, int) or timeout < 1 or timeout > 60:
            raise ValueError(f"Timeout must be 1-60 minutes, got: {timeout}")
        return timeout

    def _validate_script_path(self) -> Path:
        """Validate script exists and is in expected location."""
        script = (Path(__file__).parent / "test-feeder-image.py").resolve()

        if not script.exists():
            raise ValueError(f"Test script not found: {script}")

        # Ensure it's actually in our directory (prevent path traversal)
        expected_dir = Path(__file__).parent.resolve()
        if not script.is_relative_to(expected_dir):
            raise ValueError(f"Test script must be in {expected_dir}")

        return script

    def _validate_python_path(self) -> Path:
        """Validate venv python exists."""
        python = (Path(__file__).parent / "venv" / "bin" / "python").resolve()

        if not python.exists():
            raise ValueError(f"Virtual environment not found at {python}. Run ./setup-dev.sh to create it.")

        return Path(__file__).parent / "venv" / "bin" / "python"

    def execute_test(self, test_item: Dict) -> Dict[str, str]:
        """Execute a test with timeout."""
        test_id = test_item["id"]
        url = test_item["url"]

        # Validate URL doesn't contain shell metacharacters
        dangerous_chars = [";", "&", "|", "`", "$", "\n", "\r"]
        if any(c in url for c in dangerous_chars):
            return {"success": False, "message": f"URL contains invalid characters and was rejected for security"}

        logging.info(f"Starting test {test_id} for URL: {url}")

        try:
            # Build command
            cmd = [
                str(self.venv_python),
                str(self.script_path),
                "--test-setup",  # Include the web UI test
                "--timeout",
                str(self.timeout_minutes),
                url,
                self.rpi_ip,
                self.kasa_ip,
            ]

            logging.info(f"Executing command: {' '.join(cmd)}")

            # Execute with timeout
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_minutes * 60,  # Convert to seconds
            )

            duration = time.time() - start_time

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Test completed successfully in {duration:.1f}s",
                    "stdout": result.stdout,
                    "duration": duration,
                }
            else:
                return {
                    "success": False,
                    "message": f"Test failed with return code {result.returncode}",
                    "stderr": result.stderr,
                    "stdout": result.stdout,
                    "duration": duration,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "message": f"Test timed out after {self.timeout_minutes} minutes"}
        except Exception as e:
            return {"success": False, "message": f"Test execution error: {str(e)}"}


class ADSBTestService:
    """Main service class."""

    def __init__(self, config: Dict):
        self.config = config
        self.test_queue = TestQueue()
        self.url_validator = GitHubValidator()
        self.test_executor = TestExecutor(
            rpi_ip=config["rpi_ip"], kasa_ip=config["kasa_ip"], timeout_minutes=config.get("timeout_minutes", 10)
        )

        # API key authentication
        api_keys = config.get("api_keys", {})
        self.auth = APIKeyAuth(api_keys)

        # Flask app
        self.app = Flask(__name__)
        self.setup_routes()

        # Queue processing
        self.processing = False
        self.processor_thread = None

    def setup_routes(self):
        """Setup Flask routes."""

        @self.app.route("/api/trigger-boot-test", methods=["POST"])
        @self.auth.require_auth
        def trigger_test():
            """API endpoint to trigger a boot test (requires authentication)."""
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON data provided"}), 400

                url = data.get("url")
                if not url:
                    return jsonify({"error": "No 'url' field provided"}), 400

                requester_ip = request.environ.get("REMOTE_ADDR", "unknown")
                user_id = getattr(request, "user_id", "unknown")

                # Validate URL
                validation = self.url_validator.validate_url(url)
                if not validation["valid"]:
                    return jsonify({"error": f"Invalid URL: {validation['error']}"}), 400

                # Add to queue
                result = self.test_queue.add_test(url, requester_ip)

                logging.info(f"Test request from {user_id} ({requester_ip}): {result}")
                return jsonify(result)

            except Exception as e:
                logging.error(f"Error processing test request: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/status", methods=["GET"])
        @self.auth.require_auth
        def get_status():
            """Get service status and queue information (requires authentication)."""
            return jsonify(
                {
                    "status": "running",
                    "queue_size": self.test_queue.queue.qsize(),
                    "processing": self.processing,
                    "config": {
                        "rpi_ip": self.config["rpi_ip"],
                        "kasa_ip": self.config["kasa_ip"],
                        "timeout_minutes": self.config.get("timeout_minutes", 10),
                    },
                }
            )

        @self.app.route("/health", methods=["GET"])
        def health_check():
            """Health check endpoint (unauthenticated for monitoring)."""
            return jsonify({"status": "healthy"}), 200

    def start_queue_processor(self):
        """Start the queue processing thread."""
        if self.processor_thread and self.processor_thread.is_alive():
            return

        self.processing = True
        self.processor_thread = threading.Thread(target=self._process_queue)
        self.processor_thread.daemon = True
        self.processor_thread.start()
        logging.info("Queue processor started")

    def _process_queue(self):
        """Process the test queue."""
        while self.processing:
            try:
                test_item = self.test_queue.get_next_test()
                if test_item:
                    logging.info(f"Processing test {test_item['id']}")

                    # Execute test
                    result = self.test_executor.execute_test(test_item)

                    # Mark as completed
                    self.test_queue.mark_completed(test_item["id"], result["success"], result["message"])

                    # Log result
                    if result["success"]:
                        logging.info(f"✅ Test {test_item['id']} PASSED")
                    else:
                        logging.error(f"❌ Test {test_item['id']} FAILED: {result['message']}")

                else:
                    # No tests in queue, wait a bit
                    time.sleep(5)

            except Exception as e:
                logging.error(f"Error in queue processor: {e}")
                time.sleep(10)

    def stop_queue_processor(self):
        """Stop the queue processor."""
        self.processing = False
        if self.processor_thread:
            self.processor_thread.join(timeout=30)
        logging.info("Queue processor stopped")

    def run(self, host: str = "0.0.0.0", port: int = 8080):
        """Run the Flask service."""
        logging.info(f"Starting ADS-B Test Service on {host}:{port}")
        logging.info(f"Configuration: RPi={self.config['rpi_ip']}, Kasa={self.config['kasa_ip']}")

        self.start_queue_processor()

        try:
            self.app.run(host=host, port=port, debug=False)
        except KeyboardInterrupt:
            logging.info("Service interrupted by user")
        finally:
            self.stop_queue_processor()


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration for systemd service."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def load_config(config_file: str = "/etc/adsb-test-service/config.json") -> Dict:
    """Load configuration from file."""
    config_path = Path(config_file)

    if not config_path.exists():
        # Create default config
        default_config = {
            "rpi_ip": "192.168.77.190",
            "kasa_ip": "192.168.22.147",
            "timeout_minutes": 10,
            "host": "0.0.0.0",
            "port": 8080,
            "log_level": "INFO",
            "api_keys": {
                # Format: "api_key": "user_identifier"
                # Generate keys with: python3 generate-api-key.py
                # Example: "abc123def456...": "github-ci"
            },
        }

        # Create directory if needed
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(default_config, f, indent=2)

        logging.warning(f"Created default config at {config_path}")
        logging.warning("⚠️  No API keys configured. Generate keys with: python3 generate-api-key.py")
        return default_config

    with open(config_path, "r") as f:
        return json.load(f)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ADS-B Test Service")
    parser.add_argument("--config", default="/etc/adsb-test-service/config.json", help="Configuration file path")
    parser.add_argument("--host", help="Host to bind to (overrides config)")
    parser.add_argument("--port", type=int, help="Port to bind to (overrides config)")
    parser.add_argument("--log-level", help="Log level (overrides config)")

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Override with command line args
    if args.host:
        config["host"] = args.host
    if args.port:
        config["port"] = args.port
    if args.log_level:
        config["log_level"] = args.log_level

    # Setup logging
    setup_logging(config.get("log_level", "INFO"))

    # Create and run service
    service = ADSBTestService(config)

    # Handle shutdown signals
    def signal_handler(signum, frame):
        logging.info(f"Received signal {signum}, shutting down...")
        service.stop_queue_processor()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    service.run(config["host"], config["port"])


if __name__ == "__main__":
    main()
