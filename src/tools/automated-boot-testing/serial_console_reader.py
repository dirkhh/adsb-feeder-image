#!/usr/bin/env python3
"""
Serial Console Reader - Background thread for monitoring serial console output.

Provides thread-safe buffering and querying of serial console output during boot testing.
"""

import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("⚠️  pyserial not available - serial console monitoring disabled")


class SerialConsoleReader:
    """
    Background thread that reads from serial console and buffers output.
    Thread-safe access to buffered lines.
    """

    def __init__(
        self,
        device_path: str,
        baud_rate: int = 115200,
        max_buffer_lines: int = 1000,
        log_prefix: str = "serial",
        realtime_log_file: Optional[str] = None,
    ):
        """
        Initialize serial console reader.

        Args:
            device_path: Path to serial device (e.g., /dev/ttyUSB0)
            baud_rate: Serial baud rate (default: 115200)
            max_buffer_lines: Max lines to keep in buffer (older lines dropped)
            log_prefix: Prefix for log files (default: "serial")
            realtime_log_file: Optional path to write logs in real-time (for monitoring)
        """
        self.device_path = device_path
        self.baud_rate = baud_rate
        self.max_buffer_lines = max_buffer_lines
        self.log_prefix = log_prefix
        self.realtime_log_file = realtime_log_file

        # Thread-safe circular buffer
        self._buffer = deque(maxlen=max_buffer_lines)
        self._buffer_lock = threading.Lock()

        # Background thread control
        self._thread = None
        self._running = False
        self._serial_port = None
        self._log_file_handle = None

        # Deduplication tracking (suppress consecutive identical lines)
        self._last_line = None
        self._repeat_count = 0
        self._recent_read = 0

    def start(self) -> bool:
        """
        Start background reading thread.

        Returns:
            True if started successfully, False if device can't be opened
        """
        if not SERIAL_AVAILABLE:
            print("⚠️  pyserial not installed - cannot monitor serial console")
            return False

        if not self.device_path:
            print("ℹ️  No serial device configured - serial monitoring disabled")
            return False

        if self._running:
            print("⚠️  Serial reader already running")
            return True

        # Try to open serial device
        try:
            self._serial_port = serial.Serial(
                port=self.device_path,
                baudrate=self.baud_rate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1.0,  # 1 second read timeout
            )
            print(f"✓ Opened serial console: {self.device_path} @ {self.baud_rate} baud")
        except serial.SerialException as e:
            print(f"⚠️  Failed to open serial device {self.device_path}: {e}")
            return False
        except Exception as e:
            print(f"⚠️  Unexpected error opening {self.device_path}: {e}")
            return False

        # Open real-time log file if configured
        if self.realtime_log_file:
            try:
                # Create directory if needed
                log_path = Path(self.realtime_log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)

                # Open file for writing (unbuffered for real-time monitoring)
                self._log_file_handle = open(self.realtime_log_file, 'w', buffering=1)
                print(f"✓ Opened real-time serial log: {self.realtime_log_file}")
            except Exception as e:
                print(f"⚠️  Failed to open real-time log file {self.realtime_log_file}: {e}")
                self._log_file_handle = None

        # Start background thread
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        print(f"✓ Started serial console reader thread")

        return True

    def stop(self):
        """Stop background reading thread and close device."""
        if not self._running:
            return

        print("Stopping serial console reader...")
        self._running = False

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        # Add final repeat summary if needed
        with self._buffer_lock:
            if self._repeat_count > 0:
                summary = f"[previous line repeated {self._repeat_count} times]"
                self._buffer.append(summary)
                # Write final summary to log file too
                if self._log_file_handle:
                    try:
                        self._log_file_handle.write(summary + '\n')
                        self._log_file_handle.flush()
                    except Exception:
                        pass
                self._repeat_count = 0

        # Close real-time log file
        if self._log_file_handle:
            try:
                self._log_file_handle.close()
                print(f"✓ Closed real-time serial log")
            except Exception as e:
                print(f"⚠️  Error closing log file: {e}")
            self._log_file_handle = None

        # Close serial port
        if self._serial_port:
            try:
                self._serial_port.close()
                print("✓ Closed serial device")
            except Exception as e:
                print(f"⚠️  Error closing serial device: {e}")

        self._serial_port = None
        self._thread = None

    def _read_loop(self):
        """Background thread that reads from serial device and buffers lines."""
        print(f"Serial reader thread started for {self.device_path}")

        try:
            while self._running:
                try:
                    # Read a line from serial (timeout is 1 second)
                    if self._serial_port and self._serial_port.in_waiting > 0:
                        line = self._serial_port.readline()

                        # Decode and strip whitespace
                        try:
                            line_str = line.decode("utf-8", errors="replace").rstrip()
                        except Exception:
                            line_str = str(line).rstrip()

                        # Only add non-empty lines
                        if line_str:
                            with self._buffer_lock:
                                # Deduplicate: suppress consecutive identical lines
                                if line_str == self._last_line:
                                    # Same as previous line - increment counter, don't add
                                    self._repeat_count += 1
                                else:
                                    # Different line - add summary if previous was repeated
                                    if self._repeat_count > 0:
                                        summary = f"[previous line repeated {self._repeat_count} times]"
                                        self._buffer.append(summary)
                                        # Write summary to real-time log
                                        if self._log_file_handle:
                                            try:
                                                self._log_file_handle.write(summary + '\n')
                                                self._log_file_handle.flush()
                                            except Exception:
                                                pass
                                        self._repeat_count = 0

                                    # Add the new line
                                    self._buffer.append(line_str)
                                    self._last_line = line_str

                                    # Write to real-time log file
                                    if self._log_file_handle:
                                        try:
                                            self._log_file_handle.write(line_str + '\n')
                                            self._log_file_handle.flush()
                                        except Exception:
                                            # Silently ignore write errors to avoid spam
                                            pass

                    else:
                        # No data available, sleep briefly to avoid busy-waiting
                        time.sleep(0.1)

                except serial.SerialException as e:
                    print(f"⚠️  Serial device error: {e}")
                    print("   Serial reader stopping due to device error")
                    break
                except Exception as e:
                    print(f"⚠️  Unexpected error reading serial: {e}")
                    # Continue reading despite errors
                    time.sleep(0.5)

        finally:
            print("Serial reader thread exiting")

    def get_buffer_size(self) -> int:
        """Get current number of lines in buffer (thread-safe)."""
        with self._buffer_lock:
            return len(self._buffer)

    def is_running(self) -> bool:
        """Check if background thread is running."""
        return self._running and self._thread and self._thread.is_alive()

    def get_recent(self, n: int = 100, start_from_last: bool = False) -> List[str]:
        """
        Get last N lines from buffer (thread-safe).

        Args:
            n: Number of recent lines to retrieve

        Returns:
            List of recent lines (oldest first)
        """
        with self._buffer_lock:
            # deque doesn't support negative indexing, so convert to list
            buffer_list = list(self._buffer)
            if start_from_last:
                # only consider lines read since the last get_recent call with that flag set
                entries_total = len(buffer_list)
                buffer_list = buffer_list[self._recent_read:]
                self._recent_read = entries_total
            # Return last N lines
            if n >= len(buffer_list):
                return buffer_list
            else:
                return buffer_list[-n:]

    def search_recent(
        self, pattern: str, max_lines: int = 100, regex: bool = False
    ) -> bool:
        """
        Search for string/pattern in last N lines.

        Args:
            pattern: String or regex pattern to search for
            max_lines: Maximum number of recent lines to search
            regex: If True, treat pattern as regex; if False, simple substring match

        Returns:
            True if pattern was found, False otherwise
        """
        recent_lines = self.get_recent(max_lines, start_from_last=True)
        if not recent_lines:
            return False

        if regex:
            try:
                compiled_pattern = re.compile(pattern)
                for line in recent_lines:
                    if compiled_pattern.search(line):
                        return True
            except re.error as e:
                print(f"⚠️  Invalid regex pattern '{pattern}': {e}")
                return False
        else:
            # Simple substring search
            for line in recent_lines:
                if pattern in line:
                    return True

        return False

    def wait_for_pattern(
        self, pattern: str, timeout: int = 30, regex: bool = False, check_interval: float = 0.5
    ) -> Tuple[bool, Optional[str]]:
        """
        Wait until pattern appears in output or timeout.

        Args:
            pattern: String or regex pattern to wait for
            timeout: Maximum seconds to wait
            regex: If True, treat pattern as regex
            check_interval: How often to check buffer (seconds)

        Returns:
            Tuple of (found, matching_line)
            - found: True if pattern was found before timeout
            - matching_line: The line that matched, or None if not found
        """
        if regex:
            try:
                compiled_pattern = re.compile(pattern)
            except re.error as e:
                print(f"⚠️  Invalid regex pattern '{pattern}': {e}")
                return (False, None)
        else:
            compiled_pattern = None

        start_time = time.time()

        # Keep track of last line checked to avoid re-checking same lines
        last_checked_size = 0

        while time.time() - start_time < timeout:
            with self._buffer_lock:
                current_size = len(self._buffer)

                # Only check new lines since last check
                if current_size > last_checked_size:
                    buffer_list = list(self._buffer)
                    new_lines = buffer_list[last_checked_size:]

                    for line in new_lines:
                        if compiled_pattern:
                            if compiled_pattern.search(line):
                                return (True, line)
                        else:
                            if pattern in line:
                                return (True, line)

                    last_checked_size = current_size

            # Wait before checking again
            time.sleep(check_interval)

        return (False, None)

    def save_to_file(self, filepath: str) -> bool:
        """
        Save buffer contents to file.

        Args:
            filepath: Path to save file

        Returns:
            True if saved successfully
        """
        try:
            with self._buffer_lock:
                lines = list(self._buffer)

            with open(filepath, "w") as f:
                f.write("\n".join(lines))
                f.write("\n")

            print(f"✓ Saved {len(lines)} lines of serial console output to {filepath}")
            return True

        except Exception as e:
            print(f"⚠️  Failed to save serial output to {filepath}: {e}")
            return False


if __name__ == "__main__":
    # Simple test
    import sys

    if len(sys.argv) < 2:
        print("Usage: serial_console_reader.py <device_path>")
        print("Example: serial_console_reader.py /dev/ttyUSB0")
        sys.exit(1)

    device = sys.argv[1]
    reader = SerialConsoleReader(device)

    if reader.start():
        print("\nReading from serial console (Ctrl+C to stop)...")
        print("Buffer will show last 1000 lines")
        print("-" * 60)

        try:
            while True:
                time.sleep(1)
                print(f"\rBuffer: {reader.get_buffer_size()} lines", end="", flush=True)
        except KeyboardInterrupt:
            print("\n\nStopping...")
            reader.stop()
            print(f"\nFinal buffer size: {reader.get_buffer_size()} lines")
    else:
        print("Failed to start serial reader")
        sys.exit(1)
