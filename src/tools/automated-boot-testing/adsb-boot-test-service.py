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
import os
import signal
import subprocess
import sys
import threading
import time
from functools import wraps
from pathlib import Path
from subprocess import DEVNULL, check_output
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from flask import Flask, g, jsonify, request
from metrics import TestMetrics  # type: ignore # noqa: E402


def keys_match(priv, pub):
    """Check if private and public SSH keys match by comparing fingerprints."""
    priv_fingerprint = check_output(["ssh-keygen", "-lf", str(priv)], stderr=DEVNULL, text=True).split()[1]
    pub_fingerprint = check_output(["ssh-keygen", "-lf", pub], stderr=DEVNULL, text=True).split()[1]
    return priv_fingerprint == pub_fingerprint


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
            logging.debug(f"Authenticated request from user: {user_id}")

            # Add user_id to request context for use in endpoint
            g.user_id = user_id

            return f(*args, **kwargs)

        return decorated_function


class GitHubValidator:
    """Validates GitHub release URLs."""

    def __init__(self, allowed_repo: str = "dirkhh/adsb-feeder-image"):
        self.allowed_repo = allowed_repo
        self.allowed_domains = ["github.com", "githubusercontent.com"]

    def validate_url(self, url: str) -> Dict[str, Any]:
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
        patterns = [
            "/releases/download/",
            "/archive/refs/tags/",
            ".img.xz",
            ".img.gz",
            ".qcow2.xz",  # Add support for VM images
            ".zip",
            ".tar.gz",
        ]
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

    def __init__(
        self,
        rpi_ip: str,
        power_toggle_script: str,
        ssh_key: str,
        timeout_minutes: int = 10,
        config: Optional[Dict[str, Any]] = None,
    ):
        # Validate all inputs at initialization - fail fast if invalid
        self.rpi_ip = self._validate_ip(rpi_ip, "rpi_ip")
        self.power_toggle_script = self._validate_power_toggle_script(power_toggle_script)
        self.ssh_key = self._validate_ssh_key(ssh_key)
        self.timeout_minutes = self._validate_timeout(timeout_minutes)
        self.script_path = self._validate_script_path()
        self.venv_python = self._validate_python_path()
        self.config = config or {}

    def _validate_ip(self, ip: str, name: str) -> str:
        """Validate IP address format - simple and clear."""
        import ipaddress

        try:
            ipaddress.ip_address(ip)
            return ip
        except ValueError:
            raise ValueError(f"Invalid {name}: '{ip}' is not a valid IP address")

    def _validate_ssh_key(self, ssh_key: str) -> str:
        """Validate SSH key argument -- a file path to the SSH key."""
        if not ssh_key:
            raise ValueError("SSH key is required")
        ssh_key_path = Path(ssh_key)
        ssh_pub_key_path = ssh_key_path.with_suffix(".pub")
        if not ssh_key_path.exists():
            raise ValueError(f"SSH key file not found: {ssh_key_path}")
        if not ssh_key_path.is_file():
            raise ValueError(f"SSH key is not a file: {ssh_key_path}")
        if not ssh_pub_key_path.exists():
            raise ValueError(f"SSH public key file not found: {ssh_pub_key_path}")
        if not ssh_pub_key_path.is_file():
            raise ValueError(f"SSH public key is not a file: {ssh_pub_key_path}")
        # test if private and public keys match
        if not keys_match(ssh_key_path, ssh_pub_key_path):
            raise ValueError(f"SSH key and public key do not match: {ssh_key_path} {ssh_pub_key_path}")
        return str(ssh_key_path)

    def _validate_power_toggle_script(self, script_path: str) -> str:
        """Validate power toggle script path."""
        if not script_path:
            raise ValueError("Power toggle script path is required")
        script = Path(script_path)
        if not script.exists():
            raise ValueError(f"Power toggle script not found: {script}")
        if not script.is_file():
            raise ValueError(f"Power toggle script is not a file: {script}")
        if not os.access(script, os.X_OK):
            raise ValueError(f"Power toggle script is not executable: {script}")
        return str(script)

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

    def execute_test(self, test_item: Dict, metrics_id: Optional[int] = None) -> Dict[str, Any]:
        """Execute a test with timeout."""
        test_id = test_item["id"]
        url = test_item["url"]

        # Validate URL doesn't contain shell metacharacters
        dangerous_chars = [";", "&", "|", "`", "$", "\n", "\r"]
        if any(c in url for c in dangerous_chars):
            return {"success": False, "message": "URL contains invalid characters and was rejected for security"}

        logging.info(f"Starting test {test_id} for URL: {url}")

        try:
            # Build command
            cmd = [
                str(self.venv_python),
                str(self.script_path),
                "--timeout",
                str(self.timeout_minutes),
                "--ssh-key",
                str(self.ssh_key),
            ]

            # Add metrics tracking if available
            if metrics_id is not None:
                cmd.extend(["--metrics-id", str(metrics_id)])

            # Add serial console if configured
            serial_console = self.config.get("serial_console", "")
            if serial_console:
                cmd.extend(["--serial-console", serial_console])
                serial_baud = self.config.get("serial_baud", 115200)
                cmd.extend(["--serial-baud", str(serial_baud)])

            # Add keep-on-failure flag if configured (for debugging)
            keep_on_failure = self.config.get("keep_on_failure", False)
            if keep_on_failure:
                cmd.append("--keep-on-failure")

            # Add positional arguments
            cmd.extend([url, self.rpi_ip, self.power_toggle_script])

            logging.info(f"Executing command: {' '.join(cmd)}")

            # Execute with timeout and real-time output forwarding
            start_time = time.time()

            # Use Popen to capture output in real-time for journalctl
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Forward output in real-time to journalctl
            output_lines = []
            try:
                if process.stdout:
                    for line in process.stdout:
                        # Log to journalctl in real-time
                        logging.info(line.rstrip())
                        output_lines.append(line)

                # Wait for process to complete with timeout
                returncode = process.wait(timeout=self.timeout_minutes * 60)

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return {"success": False, "message": f"Test timed out after {self.timeout_minutes} minutes"}

            duration = time.time() - start_time
            output = "".join(output_lines)

            if returncode == 0:
                return {
                    "success": True,
                    "message": f"Test completed successfully in {duration:.1f}s",
                    "stdout": output,
                    "duration": duration,
                }
            else:
                return {
                    "success": False,
                    "message": f"Test failed with return code {returncode}",
                    "stdout": output,
                    "duration": duration,
                }

        except Exception as e:
            return {"success": False, "message": f"Test execution error: {str(e)}"}


class ADSBTestService:
    """Main service class."""

    def __init__(self, config: Dict):
        self.config = config
        self.url_validator = GitHubValidator()
        self.test_executor = TestExecutor(
            rpi_ip=config["rpi_ip"],
            power_toggle_script=config["power_toggle_script"],
            ssh_key=config["ssh_key"],
            timeout_minutes=config.get("timeout_minutes", 10),
            config=config,
        )

        # API key authentication
        api_keys = config.get("api_keys", {})
        self.auth = APIKeyAuth(api_keys)

        # Metrics tracking
        self.metrics = TestMetrics()
        logging.info("Metrics tracking initialized")

        # Flask app
        self.app = Flask(__name__)
        self.setup_routes()

        # Queue processing
        self.processing = False
        self.processor_thread: Optional[threading.Thread] = None

    def _detect_test_type(self, image_url: str) -> str:
        """
        Detect test type from image URL pattern.

        Args:
            image_url: URL of the image to test

        Returns:
            "vm" if Proxmox qcow2 image, "rpi" otherwise
        """
        return "vm" if "Proxmox-x86_64.qcow2" in image_url else "rpi"

    def setup_routes(self):
        """Setup Flask routes."""

        @self.app.route("/api/trigger-boot-test", methods=["POST"])
        @self.auth.require_auth
        def trigger_test():
            """
            API endpoint to trigger a boot test (requires authentication).

            The test will be queued in the database and processed by the test executor.
            GitHub context is optional and used for posting results back to GitHub.
            """
            try:
                data = request.get_json()
                if not data:
                    return jsonify({"error": "No JSON data provided"}), 400

                url = data.get("url")
                if not url:
                    return jsonify({"error": "No 'url' field provided"}), 400

                # Extract GitHub context if provided
                github_context = data.get("github_context", {})
                release_id = github_context.get("release_id")

                requester_ip = request.environ.get("REMOTE_ADDR", "unknown")
                user_id = getattr(g, "user_id", "unknown")

                # Validate URL
                validation = self.url_validator.validate_url(url)
                if not validation["valid"]:
                    return jsonify({"error": f"Invalid URL: {validation['error']}"}), 400

                # Check for duplicates
                duplicate = self.metrics.check_duplicate(url, release_id)
                if duplicate:
                    logging.debug(
                        f"Duplicate test ignored: URL={url}, release_id={release_id}, "
                        f"previous test_id={duplicate['test_id']}, {duplicate['minutes_ago']} minutes ago"
                    )
                    return (
                        jsonify(
                            {
                                "status": "ignored",
                                "message": f"Duplicate test from {duplicate['minutes_ago']} minutes ago",
                                "previous_test_id": duplicate["test_id"],
                            }
                        ),
                        200,
                    )

                logging.info(
                    f"Triggering boot test for URL: {url} from {requester_ip} by {user_id} with GitHub context: {github_context}"
                )

                if not github_context:
                    logging.warning(f"No GitHub context provided, URL: {url}")

                # Create test record in 'queued' state
                test_id = self.metrics.start_test(
                    image_url=url,
                    triggered_by="github_webhook" if github_context else "api",
                    trigger_source=github_context.get("commit_sha") or user_id,
                    rpi_ip=self.config["rpi_ip"],
                    github_event_type=github_context.get("event_type"),
                    github_release_id=github_context.get("release_id"),
                    github_pr_number=github_context.get("pr_number"),
                    github_commit_sha=github_context.get("commit_sha"),
                    github_workflow_run_id=github_context.get("workflow_run_id"),
                )

                logging.info(f"Test queued: ID={test_id}, URL={url}, GitHub={github_context.get('event_type', 'none')}")

                return jsonify(
                    {
                        "test_id": test_id,
                        "status": "queued",
                        "message": "Test queued successfully",
                        "github_context": github_context if github_context else None,
                    }
                )

            except Exception as e:
                logging.error(f"Error processing test request: {e}")
                return jsonify({"error": str(e)}), 500

        @self.app.route("/health", methods=["GET"])
        def health_check():
            """Health check endpoint (unauthenticated for monitoring)."""
            return jsonify({"status": "healthy"}), 200

        @self.app.route("/api/metrics/recent", methods=["GET"])
        @self.auth.require_auth
        def get_recent_metrics():
            """Get recent test metrics (requires authentication)."""
            limit = request.args.get("limit", 10, type=int)
            results = self.metrics.get_recent_results(limit=limit)
            return jsonify(results)

        @self.app.route("/api/metrics/stats", methods=["GET"])
        @self.auth.require_auth
        def get_stats():
            """Get test statistics (requires authentication)."""
            days = request.args.get("days", 7, type=int)
            stats = self.metrics.get_stats(days=days)
            return jsonify(stats)

        @self.app.route("/api/metrics/failures", methods=["GET"])
        @self.auth.require_auth
        def get_failures():
            """Get recent failures (requires authentication)."""
            limit = request.args.get("limit", 10, type=int)
            failures = self.metrics.get_failures(limit=limit)
            return jsonify(failures)

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
        """Process the test queue - polls database for queued tests."""
        logging.info("Queue processor started - polling for queued tests")

        while self.processing:
            try:
                # Get queued tests from database
                queued_tests = self.metrics.get_queued_tests()

                if queued_tests:
                    logging.info(f"Found {len(queued_tests)} queued test(s)")

                    # Process first test (FIFO)
                    test = queued_tests[0]
                    test_id = test["id"]

                    # Mark test as running
                    self.metrics.update_test_status(test_id, "running")
                    logging.info(f"Starting test {test_id}: {test['image_url']}")

                    try:
                        # Execute test
                        result = self._execute_test(test)

                        # Mark as passed or failed
                        final_status = "passed" if result["success"] else "failed"
                        self.metrics.complete_test(
                            test_id, status=final_status, error_message=result.get("error"), error_stage=result.get("error_stage")
                        )

                        if result["success"]:
                            logging.info(f"✅ Test {test_id} PASSED")
                        else:
                            logging.error(f"❌ Test {test_id} FAILED: {result.get('error')}")

                    except Exception as e:
                        logging.error(f"Test {test_id} failed with exception: {e}")
                        self.metrics.complete_test(test_id, status="failed", error_message=str(e), error_stage="executor")

                else:
                    # No tests in queue, wait a bit
                    time.sleep(10)

            except Exception as e:
                logging.error(f"Error in queue processor: {e}")
                time.sleep(10)

    def stop_queue_processor(self):
        """Stop the queue processor."""
        self.processing = False
        if self.processor_thread:
            self.processor_thread.join(timeout=30)
        logging.info("Queue processor stopped")

    def _execute_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute test - routes to appropriate handler based on image type.

        Args:
            test: Test record from database

        Returns:
            Dict with success, error, error_stage, duration
        """
        image_url = test["image_url"]
        test_type = self._detect_test_type(image_url)

        logging.info(f"Detected test type: {test_type} for URL: {image_url}")

        if test_type == "vm":
            return self._execute_vm_test(test)
        else:
            return self._execute_rpi_test(test)

    def _execute_vm_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute VM test using test-vm-image.py script.

        Args:
            test: Test record from database

        Returns:
            Dict with success, error, error_stage, duration
        """
        test_id = test["id"]
        image_url = test["image_url"]
        duration: float = 0.0
        process: Optional[subprocess.Popen] = None
        returncode: Optional[int] = None

        # Validate VM config exists
        required_config = ["vm_server_ip", "vm_ssh_key", "vm_bridge"]
        missing = [key for key in required_config if not self.config.get(key)]
        if missing:
            return {
                "success": False,
                "error": f"VM testing not configured (missing: {', '.join(missing)})",
                "error_stage": "configuration",
            }

        # Validate URL doesn't contain shell metacharacters
        dangerous_chars = [";", "&", "|", "`", "$", "\n", "\r"]
        if any(c in image_url for c in dangerous_chars):
            return {
                "success": False,
                "error": "URL contains invalid characters and was rejected for security",
                "error_stage": "validation",
            }

        try:
            # Build VM test command
            vm_script = Path(__file__).parent / "test-vm-image.py"
            cmd = [
                str(self.test_executor.venv_python),
                str(vm_script),
                image_url,
                "--vm-server",
                self.config["vm_server_ip"],
                "--vm-ssh-key",
                self.config["vm_ssh_key"],
                "--vm-bridge",
                self.config["vm_bridge"],
                "--metrics-id",
                str(test_id),
                "--metrics-db",
                str(self.metrics.db_path),
                "--timeout",
                str(self.test_executor.timeout_minutes),
            ]

            # Add optional VM config
            if self.config.get("vm_memory_mb"):
                cmd.extend(["--vm-memory", str(self.config["vm_memory_mb"])])
            if self.config.get("vm_cpus"):
                cmd.extend(["--vm-cpus", str(self.config["vm_cpus"])])

            # Add keep-on-failure flag if configured (for debugging)
            keep_on_failure = self.config.get("keep_on_failure", False)
            if keep_on_failure:
                cmd.append("--keep-on-failure")

            logging.info(f"Executing VM test command: {' '.join(cmd)}")

            # Execute with timeout and real-time output forwarding
            start_time = time.time()

            # Use Popen to capture output in real-time for journalctl
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Forward output in real-time to journalctl
            output_lines = []
            try:
                if process.stdout:
                    for line in process.stdout:
                        # Log to journalctl in real-time
                        logging.info(line.rstrip())
                        output_lines.append(line)

                # Wait for process to complete with timeout
                returncode = process.wait(timeout=self.test_executor.timeout_minutes * 60)

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return {
                    "success": False,
                    "error": f"VM test timed out after {self.test_executor.timeout_minutes} minutes",
                    "error_stage": "timeout",
                }

            duration = time.time() - start_time

            # Check exit code
            success = returncode == 0
            return {
                "success": success,
                "error": None if success else "VM test script failed",
                "error_stage": None if success else "test_execution",
                "duration": duration,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_stage": "executor",
                "duration": duration,
            }

    def _execute_rpi_test(self, test: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute RPi boot test using test-feeder-image.py.

        Returns dict with success, error, error_stage.
        """
        test_id = test["id"]
        image_url = test["image_url"]
        duration: float = 0.0
        process: Optional[subprocess.Popen] = None
        returncode: Optional[int] = None

        # Validate URL doesn't contain shell metacharacters
        dangerous_chars = [";", "&", "|", "`", "$", "\n", "\r"]
        if any(c in image_url for c in dangerous_chars):
            return {
                "success": False,
                "error": "URL contains invalid characters and was rejected for security",
                "error_stage": "validation",
            }

        try:
            # Build test command
            cmd = [
                str(self.test_executor.venv_python),
                str(self.test_executor.script_path),
                image_url,
                self.config["rpi_ip"],
                self.config["power_toggle_script"],
                "--metrics-id",
                str(test_id),
                "--metrics-db",
                str(self.metrics.db_path),
                "--timeout",
                str(self.test_executor.timeout_minutes),
                "--ssh-key",
                str(self.test_executor.ssh_key),
            ]

            # Add optional arguments
            if self.config.get("serial_console"):
                cmd.extend(["--serial-console", self.config["serial_console"]])
                cmd.extend(["--serial-baud", str(self.config.get("serial_baud", 115200))])

            logging.info(f"Executing command: {' '.join(cmd)}")

            # Execute with timeout and real-time output forwarding
            start_time = time.time()

            # Use Popen to capture output in real-time for journalctl
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Forward output in real-time to journalctl
            output_lines = []
            try:
                if process.stdout:
                    for line in process.stdout:
                        # Log to journalctl in real-time
                        logging.info(line.rstrip())
                        output_lines.append(line)

                # Wait for process to complete with timeout
                returncode = process.wait(timeout=self.test_executor.timeout_minutes * 60)

            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                return {
                    "success": False,
                    "error": f"Test timed out after {self.test_executor.timeout_minutes} minutes",
                    "error_stage": "timeout",
                }

            duration = time.time() - start_time

            # Check exit code
            success = returncode == 0
            return {
                "success": success,
                "error": None if success else "Test script failed",
                "error_stage": None if success else "test_execution",
                "duration": duration,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_stage": "executor",
                "duration": duration,
            }

    def run(self, host: str = "0.0.0.0", port: int = 8080):
        """Run the Flask service."""
        logging.info(f"Starting ADS-B Test Service on {host}:{port}")
        logging.info(f"Configuration: RPi={self.config['rpi_ip']}, Power Toggle={self.config['power_toggle_script']}")

        self.start_queue_processor()

        try:
            self.app.run(host=host, port=port, debug=False)
        except KeyboardInterrupt:
            logging.info("Service interrupted by user")
        finally:
            self.stop_queue_processor()


def setup_logging(log_level: str = "INFO"):
    """Setup logging configuration for systemd service."""
    # Configure line-buffered output for real-time journalctl logging
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined,union-attr]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined,union-attr]

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Set werkzeug (Flask's HTTP server) to WARNING to suppress HTTP request logs
    # This prevents routine HTTP request logs from appearing at INFO level
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def load_config(config_file: str = "/etc/adsb-boot-test/config.json") -> Dict:
    """Load configuration from file."""
    config_path = Path(config_file)

    if not config_path.exists():
        # Create default config
        default_config = {
            "rpi_ip": "192.168.77.190",
            "power_toggle_script": "/opt/adsb-boot-test/power-toggle-kasa.py",
            "ssh_key": "/etc/adsb-boot-test/ssh_key",
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
    parser.add_argument("--config", default="/etc/adsb-boot-test/config.json", help="Configuration file path")
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
    def signal_handler(signum, _frame):
        logging.info(f"Received signal {signum}, shutting down...")
        service.stop_queue_processor()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    service.run(config["host"], config["port"])


if __name__ == "__main__":
    main()
