#!/usr/bin/env python3
"""
Unit tests for SerialConsoleReader

Tests the API without requiring actual serial hardware.
"""

import re
import time

from serial_console_reader import SerialConsoleReader


def test_buffer_api():
    """Test buffer operations without actual serial device."""
    # Create reader (won't start without device)
    reader = SerialConsoleReader("/dev/null", max_buffer_lines=10)

    # Manually populate buffer for testing
    test_lines = [
        "Booting Linux kernel...",
        "[ 0.123456] USB 1-1: new high-speed USB device number 2 using xhci_hcd",
        "[ 1.234567] iSCSI initiator starting",
        "[ 2.345678] iSCSI: Connection established",
        "DietPi-Boot: Phase 1",
        "DietPi-Boot: Phase 2",
        "[ 5.678901] systemd[1]: Started System Initialization",
        "DietPi login:",
        "Last login: Thu Oct 23 12:00:00 UTC 2025",
        "root@dietpi:~#",
    ]

    # Add lines to buffer (simulating serial input)
    for line in test_lines:
        reader._buffer.append(line)

    assert reader.get_buffer_size() == 10, "Buffer should have 10 lines"

    # Test get_recent
    recent_3 = reader.get_recent(3)
    assert len(recent_3) == 3, "Should return 3 lines"
    assert recent_3[-1] == "root@dietpi:~#", "Last line should be shell prompt"

    # Test search_recent - simple string
    reader._recent_read = 0  # Reset for fresh search
    found = reader.search_recent("iSCSI", max_lines=100)
    # Manually filter to verify count
    recent_lines = reader.get_recent(100)
    matches = [line for line in recent_lines if "iSCSI" in line]
    assert found, "search_recent should return True"
    assert len(matches) == 2, "Should find 2 lines with 'iSCSI'"

    # Test search_recent - regex
    reader._recent_read = 0  # Reset for fresh search
    found = reader.search_recent(r"DietPi-Boot: Phase \d", max_lines=100, regex=True)
    # Manually filter to verify count (search entire buffer, not just new lines)
    recent_lines = reader.get_recent(100)
    matches = [line for line in recent_lines if re.search(r"DietPi-Boot: Phase \d", line)]
    assert found, "search_recent should return True"
    assert len(matches) == 2, "Should find 2 DietPi boot phase lines"

    # Test search_recent - USB devices
    reader._recent_read = 0  # Reset for fresh search
    found = reader.search_recent(r"USB \d+-\d+", max_lines=100, regex=True)
    # Manually filter to verify count (search entire buffer, not just new lines)
    recent_lines = reader.get_recent(100)
    matches = [line for line in recent_lines if re.search(r"USB \d+-\d+", line)]
    assert found, "search_recent should return True"
    assert len(matches) == 1, "Should find 1 USB message"

    # Test circular buffer (max 10 lines)
    reader._buffer.append("NEW LINE 1")
    reader._buffer.append("NEW LINE 2")
    assert reader.get_buffer_size() == 10, "Buffer should stay at max size (10)"

    recent_2 = reader.get_recent(2)
    assert recent_2[-1] == "NEW LINE 2", "Should have newest line"
    assert "Booting Linux kernel..." not in reader.get_recent(100), "Oldest line should be dropped"

    # Test wait_for_pattern (with manual triggering)
    reader._buffer.clear()

    # Add lines one by one to simulate streaming
    def simulate_boot_sequence():
        time.sleep(0.2)
        reader._buffer.append("Starting boot...")
        time.sleep(0.2)
        reader._buffer.append("Loading kernel...")
        time.sleep(0.2)
        reader._buffer.append("DietPi login:")

    # Start simulation in background
    import threading

    sim_thread = threading.Thread(target=simulate_boot_sequence, daemon=True)
    sim_thread.start()

    # Wait for login prompt
    found, matching_line = reader.wait_for_pattern("login:", timeout=2)
    assert found, "Should find login: pattern"
    assert matching_line is not None and "DietPi login:" in matching_line, "Should match correct line"

    # Test wait_for_pattern timeout
    found, matching_line = reader.wait_for_pattern("NEVER_APPEARS", timeout=1)
    assert not found, "Should timeout and return False"
    assert matching_line is None, "Should return None on timeout"

    # Test save to file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:  # type: ignore[assignment]
        temp_file = f.name

    reader._buffer.clear()
    reader._buffer.append("Line 1")
    reader._buffer.append("Line 2")
    reader._buffer.append("Line 3")

    success = reader.save_to_file(temp_file)
    assert success, "Should save successfully"

    # Verify file contents
    with open(temp_file, "r") as f:  # type: ignore[assignment]
        contents = f.read()
    assert "Line 1" in contents, "Should contain Line 1"
    assert "Line 3" in contents, "Should contain Line 3"

    # Cleanup
    import os

    os.unlink(temp_file)


def test_ansi_escape_filtering():
    """Test that ANSI escape sequences are properly filtered from serial output."""
    reader = SerialConsoleReader("/dev/null")

    # Test various ANSI escape sequences that appear in boot logs
    test_cases = [
        # Format: (input_with_ansi, expected_output_without_ansi)
        (
            "\x1b[K[  \x1b[0;31m*\x1b[0;1;31m*\x1b[0m\x1b[0;31m* \x1b[0m] Job networking.service/stop",
            "[  *** ] Job networking.service/stop",
        ),
        (
            "\x1bM\r\x1b[K[  \x1b[0;31m*\x1b[0;1;31m*\x1b[0m\x1b[0;31m* \x1b[0m] Running (1min 58s / 3min)",
            "[  *** ] Running (1min 58s / 3min)",
        ),
        (
            "\x1b[0;32m  OK  \x1b[0m] Started System Logging Service.",
            "  OK  ] Started System Logging Service.",
        ),
        (
            "Normal text without any escape sequences",
            "Normal text without any escape sequences",
        ),
        (
            "\x1b[1;32mGreen Bold Text\x1b[0m",
            "Green Bold Text",
        ),
        (
            "\x1b[?25l\x1b[?25h",  # Hide/show cursor
            "",
        ),
    ]

    for i, (input_str, expected) in enumerate(test_cases, 1):
        # Use the internal method that should strip ANSI sequences
        result = reader._strip_ansi_sequences(input_str)
        assert result == expected, f"Test case {i} failed: expected {repr(expected)}, got {repr(result)}"


def test_search_recent_with_many_new_lines():
    """Test that search_recent finds patterns even when there are many new lines."""
    reader = SerialConsoleReader("/dev/null", max_buffer_lines=1000)

    # Simulate initial buffer state
    for i in range(10):
        reader._buffer.append(f"Initial line {i}")
    reader._recent_read = len(reader._buffer)  # Mark all as "read"

    # Now add 50 new lines, with the pattern appearing early (line 5 of new content)
    new_lines = [
        "[  OK  ] Stopped some service",
        "[  OK  ] Stopped another service",
        "[  OK  ] Finished systemd-reboot.service - System Reboot",
        "[  OK  ] Reached target reboot.target - System Reboot",
        "[!!!!!!] Failed to execute shutdown binary",  # Pattern is here - line 5 of new content
        "Some other message 1",
        "Some other message 2",
        # Add 43 more lines to reach 50 total
    ]
    for i in range(43):
        new_lines.append(f"Additional message {i}")

    for line in new_lines:
        reader._buffer.append(line)

    # Test 1: Without start_from_last (default), should search all recent lines
    pattern = "Failed to execute shutdown binary"
    found = reader.search_recent(pattern, max_lines=60, regex=False)
    assert found, f"Pattern '{pattern}' should be found in last 60 lines of buffer"

    # Test 2: With start_from_last=True, searches only new lines
    reader._recent_read = 10  # Reset to start of new content

    shutdown_hang_patterns = [
        "Failed to send WATCHDOG",
        "Syncing filesystems and block devices - timed out, issuing SIGKILL",
        "rejecting I/O to offline device",
        "Failed to execute shutdown binary",
        "Transport endpoint is not connected",
    ]
    pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)

    found = reader.search_recent(pattern, max_lines=100, regex=True, start_from_last=True)
    assert found, "Pattern should be found in all new lines when using start_from_last=True"


def test_shutdown_hang_pattern_matching():
    """Test the exact scenario from test-feeder-image.py shutdown detection."""
    reader = SerialConsoleReader("/dev/null")

    # Simulate the exact serial output the user is seeing
    # BUT with ANSI codes like real serial data
    serial_lines_with_ansi = [
        "\x1b[0;32m[  OK  ]\x1b[0m Finished systemd-reboot.service - System Reboot.",
        "\x1b[0;32m[  OK  ]\x1b[0m Reached target reboot.target - System Reboot.",
        "\x1b[0;31m[!!!!!!]\x1b[0m Failed to execute shutdown binary.",
    ]

    # Simulate what _read_loop does: strip ANSI before adding to buffer
    for line_with_ansi in serial_lines_with_ansi:
        line_clean = reader._strip_ansi_sequences(line_with_ansi)
        reader._buffer.append(line_clean)

    # Test with the exact pattern from test-feeder-image.py
    shutdown_hang_patterns = [
        "Failed to send WATCHDOG",
        "Syncing filesystems and block devices - timed out, issuing SIGKILL",
        "rejecting I/O to offline device",
        "Failed to execute shutdown binary",
        "Transport endpoint is not connected",
    ]

    # Combine into single regex pattern (escape special chars for literal matching)
    pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)

    # Now test search_recent
    reader._recent_read = 0
    found = reader.search_recent(pattern, max_lines=15, regex=True)

    assert found, "Pattern should match '[!!!!!!] Failed to execute shutdown binary.' " "but search_recent returned False"


def test_repeated_search_without_new_lines():
    """Test that search_recent works when called multiple times without new serial data.

    This simulates the shutdown hang detection scenario where:
    1. Device hangs during shutdown with error in serial output
    2. We poll repeatedly but no new serial data arrives
    3. We should still detect the error pattern in recent lines each time
    """
    reader = SerialConsoleReader("/dev/null")

    # Simulate serial output during shutdown hang
    shutdown_lines = [
        "[  OK  ] Finished systemd-reboot.service - System Reboot.",
        "[  OK  ] Reached target reboot.target - System Reboot.",
        "[!!!!!!] Failed to execute shutdown binary.",
    ]

    for line in shutdown_lines:
        reader._buffer.append(line)

    shutdown_hang_patterns = [
        "Failed to send WATCHDOG",
        "Syncing filesystems and block devices - timed out, issuing SIGKILL",
        "rejecting I/O to offline device",
        "Failed to execute shutdown binary",
        "Transport endpoint is not connected",
    ]
    pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)

    # First search - should find it
    reader._recent_read = 0
    found = reader.search_recent(pattern, max_lines=15, regex=True)
    assert found, "First search should find the pattern"

    # Device is hung - NO NEW LINES are added

    # Second search - should still find it
    found = reader.search_recent(pattern, max_lines=15, regex=True)

    assert found, (
        "Second search should STILL find the pattern in recent lines, "
        "but it returns False because search_recent uses start_from_last=True "
        "which only searches lines added SINCE the last call. "
        "Since the device is hung and not producing new output, "
        "there are no new lines to search!"
    )
