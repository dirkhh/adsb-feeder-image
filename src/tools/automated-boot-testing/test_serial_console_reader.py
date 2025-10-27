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
    print("Testing SerialConsoleReader API")
    print("=" * 60)

    # Create reader (won't start without device)
    reader = SerialConsoleReader("/dev/null", max_buffer_lines=10)

    # Manually populate buffer for testing
    print("\n1. Testing buffer operations...")
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

    print(f"   Added {len(test_lines)} lines to buffer")
    print(f"   Buffer size: {reader.get_buffer_size()}")
    assert reader.get_buffer_size() == 10, "Buffer should have 10 lines"
    print("   ✓ Buffer size correct")

    # Test get_recent
    print("\n2. Testing get_recent()...")
    recent_3 = reader.get_recent(3)
    print(f"   Last 3 lines:")
    for line in recent_3:
        print(f"     - {line}")
    assert len(recent_3) == 3, "Should return 3 lines"
    assert recent_3[-1] == "root@dietpi:~#", "Last line should be shell prompt"
    print("   ✓ get_recent() working")

    # Test search_recent - simple string
    print("\n3. Testing search_recent() with simple string...")
    reader._recent_read = 0  # Reset for fresh search
    found = reader.search_recent("iSCSI", max_lines=100)
    # Manually filter to verify count
    recent_lines = reader.get_recent(100)
    matches = [line for line in recent_lines if "iSCSI" in line]
    print(f"   Found {len(matches)} lines containing 'iSCSI':")
    for line in matches:
        print(f"     - {line}")
    assert found, "search_recent should return True"
    assert len(matches) == 2, "Should find 2 lines with 'iSCSI'"
    print("   ✓ search_recent() string search working")

    # Test search_recent - regex
    print("\n4. Testing search_recent() with regex...")
    reader._recent_read = 0  # Reset for fresh search
    found = reader.search_recent(r"DietPi-Boot: Phase \d", max_lines=100, regex=True)
    # Manually filter to verify count (search entire buffer, not just new lines)
    recent_lines = reader.get_recent(100)
    matches = [line for line in recent_lines if re.search(r"DietPi-Boot: Phase \d", line)]
    print(f"   Found {len(matches)} lines matching regex:")
    for line in matches:
        print(f"     - {line}")
    assert found, "search_recent should return True"
    assert len(matches) == 2, "Should find 2 DietPi boot phase lines"
    print("   ✓ search_recent() regex search working")

    # Test search_recent - USB devices
    print("\n5. Testing search for USB devices...")
    reader._recent_read = 0  # Reset for fresh search
    found = reader.search_recent(r"USB \d+-\d+", max_lines=100, regex=True)
    # Manually filter to verify count (search entire buffer, not just new lines)
    recent_lines = reader.get_recent(100)
    matches = [line for line in recent_lines if re.search(r"USB \d+-\d+", line)]
    print(f"   Found {len(matches)} USB device messages:")
    for line in matches:
        print(f"     - {line}")
    assert found, "search_recent should return True"
    assert len(matches) == 1, "Should find 1 USB message"
    print("   ✓ USB device search working")

    # Test circular buffer (max 10 lines)
    print("\n6. Testing circular buffer (maxlen=10)...")
    reader._buffer.append("NEW LINE 1")
    reader._buffer.append("NEW LINE 2")
    print(f"   Added 2 more lines to buffer")
    print(f"   Buffer size: {reader.get_buffer_size()}")
    assert reader.get_buffer_size() == 10, "Buffer should stay at max size (10)"

    recent_2 = reader.get_recent(2)
    print(f"   Last 2 lines: {recent_2}")
    assert recent_2[-1] == "NEW LINE 2", "Should have newest line"
    assert "Booting Linux kernel..." not in reader.get_recent(100), "Oldest line should be dropped"
    print("   ✓ Circular buffer working (oldest lines dropped)")

    # Test wait_for_pattern (with manual triggering)
    print("\n7. Testing wait_for_pattern() simulation...")
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
    print(f"   Pattern 'login:' found: {found}")
    if found:
        print(f"   Matching line: {matching_line}")
    assert found, "Should find login: pattern"
    assert matching_line is not None and "DietPi login:" in matching_line, "Should match correct line"
    print("   ✓ wait_for_pattern() working")

    # Test wait_for_pattern timeout
    print("\n8. Testing wait_for_pattern() timeout...")
    found, matching_line = reader.wait_for_pattern("NEVER_APPEARS", timeout=1)
    assert not found, "Should timeout and return False"
    assert matching_line is None, "Should return None on timeout"
    print("   ✓ wait_for_pattern() timeout working")

    # Test save to file
    print("\n9. Testing save_to_file()...")
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
    print(f"   Saved to: {temp_file}")
    print("   ✓ save_to_file() working")

    # Cleanup
    import os

    os.unlink(temp_file)

    print("\n" + "=" * 60)
    print("🎉 All SerialConsoleReader API tests passed!")
    print()


def test_ansi_escape_filtering():
    """Test that ANSI escape sequences are properly filtered from serial output."""
    print("Testing ANSI Escape Sequence Filtering")
    print("=" * 60)

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

    print("\n1. Testing ANSI escape sequence stripping...")
    for i, (input_str, expected) in enumerate(test_cases, 1):
        # Use the internal method that should strip ANSI sequences
        result = reader._strip_ansi_sequences(input_str)
        print(f"\n   Test case {i}:")
        print(f"     Input:    {repr(input_str)}")
        print(f"     Expected: {repr(expected)}")
        print(f"     Result:   {repr(result)}")

        assert result == expected, f"Test case {i} failed: expected {repr(expected)}, got {repr(result)}"
        print(f"     ✓ Passed")

    print("\n" + "=" * 60)
    print("🎉 All ANSI escape sequence filtering tests passed!")
    print()


def test_search_recent_with_many_new_lines():
    """Test that search_recent finds patterns even when there are many new lines."""
    print("Testing search_recent with many new lines")
    print("=" * 60)

    reader = SerialConsoleReader("/dev/null", max_buffer_lines=1000)

    # Simulate initial buffer state
    print("\n1. Simulating initial buffer with 10 lines...")
    for i in range(10):
        reader._buffer.append(f"Initial line {i}")
    reader._recent_read = len(reader._buffer)  # Mark all as "read"
    print(f"   Buffer has {reader.get_buffer_size()} lines, _recent_read={reader._recent_read}")

    # Now add 50 new lines, with the pattern appearing early (line 5 of new content)
    print("\n2. Adding 50 new lines with pattern at line 5...")
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

    print(f"   Buffer now has {reader.get_buffer_size()} lines")
    print(f"   New lines added: {len(new_lines)}")
    print(f"   Pattern 'Failed to execute shutdown binary' is at position 5 of new content")

    # Test 1: Without start_from_last (default), should search all recent lines
    print("\n3. Testing search_recent with max_lines=60 (default behavior)...")
    print("   With start_from_last=False (default), searches last 60 lines of buffer")
    print("   Pattern is at position 15 of 60 total lines, so IS in last 60")

    pattern = "Failed to execute shutdown binary"
    found = reader.search_recent(pattern, max_lines=60, regex=False)

    print(f"   Pattern found: {found}")
    assert found, f"Pattern '{pattern}' should be found in last 60 lines of buffer"
    print("   ✓ Pattern found correctly")

    # Test 2: With start_from_last=True, searches only new lines
    print("\n4. Testing search_recent with start_from_last=True...")
    print("   This only searches NEW lines (50), and pattern is at position 5 of new lines")
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
    print(f"   Pattern found: {found}")
    assert found, "Pattern should be found in all new lines when using start_from_last=True"
    print("   ✓ Combined pattern found correctly")

    print("\n" + "=" * 60)
    print("🎉 All search_recent tests passed!")
    print()


def test_shutdown_hang_pattern_matching():
    """Test the exact scenario from test-feeder-image.py shutdown detection."""
    print("Testing shutdown hang pattern matching")
    print("=" * 60)

    reader = SerialConsoleReader("/dev/null")

    # Simulate the exact serial output the user is seeing
    # BUT with ANSI codes like real serial data
    print("\n1. Adding serial output lines WITH ANSI codes...")
    serial_lines_with_ansi = [
        "\x1b[0;32m[  OK  ]\x1b[0m Finished systemd-reboot.service - System Reboot.",
        "\x1b[0;32m[  OK  ]\x1b[0m Reached target reboot.target - System Reboot.",
        "\x1b[0;31m[!!!!!!]\x1b[0m Failed to execute shutdown binary.",
    ]

    # Simulate what _read_loop does: strip ANSI before adding to buffer
    for line_with_ansi in serial_lines_with_ansi:
        line_clean = reader._strip_ansi_sequences(line_with_ansi)
        reader._buffer.append(line_clean)
        print(f"   Raw:     {repr(line_with_ansi)}")
        print(f"   Cleaned: {repr(line_clean)}")

    # Test with the exact pattern from test-feeder-image.py
    print("\n2. Testing pattern matching (exact code from test-feeder-image.py)...")
    shutdown_hang_patterns = [
        "Failed to send WATCHDOG",
        "Syncing filesystems and block devices - timed out, issuing SIGKILL",
        "rejecting I/O to offline device",
        "Failed to execute shutdown binary",
        "Transport endpoint is not connected",
    ]

    # Combine into single regex pattern (escape special chars for literal matching)
    pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)
    print(f"   Regex pattern: {repr(pattern[:100])}...")

    # Check buffer contents
    recent = reader.get_recent(15, start_from_last=False)
    print(f"\n3. Buffer contents ({len(recent)} lines):")
    for i, line in enumerate(recent):
        print(f"   [{i}] {repr(line)}")
        # Manually check if pattern matches
        if re.search(pattern, line):
            print(f"       ^^^ MATCHES!")

    # Now test search_recent
    reader._recent_read = 0
    found = reader.search_recent(pattern, max_lines=15, regex=True)

    print(f"\n4. search_recent result: {found}")

    assert found, f"Pattern should match '[!!!!!!] Failed to execute shutdown binary.' " f"but search_recent returned False"
    print("   ✓ Pattern found correctly")

    print("\n" + "=" * 60)
    print("🎉 Shutdown hang pattern matching test passed!")
    print()


def test_repeated_search_without_new_lines():
    """Test that search_recent works when called multiple times without new serial data.

    This simulates the shutdown hang detection scenario where:
    1. Device hangs during shutdown with error in serial output
    2. We poll repeatedly but no new serial data arrives
    3. We should still detect the error pattern in recent lines each time
    """
    print("Testing repeated search_recent calls without new lines")
    print("=" * 60)

    reader = SerialConsoleReader("/dev/null")

    # Simulate serial output during shutdown hang
    print("\n1. Initial state: Adding shutdown messages...")
    shutdown_lines = [
        "[  OK  ] Finished systemd-reboot.service - System Reboot.",
        "[  OK  ] Reached target reboot.target - System Reboot.",
        "[!!!!!!] Failed to execute shutdown binary.",
    ]

    for line in shutdown_lines:
        reader._buffer.append(line)
        print(f"   {line}")

    shutdown_hang_patterns = [
        "Failed to send WATCHDOG",
        "Syncing filesystems and block devices - timed out, issuing SIGKILL",
        "rejecting I/O to offline device",
        "Failed to execute shutdown binary",
        "Transport endpoint is not connected",
    ]
    pattern = "|".join(re.escape(p) for p in shutdown_hang_patterns)

    # First search - should find it
    print("\n2. First search_recent call (should find pattern)...")
    reader._recent_read = 0
    found = reader.search_recent(pattern, max_lines=15, regex=True)
    print(f"   Result: {found}")
    assert found, "First search should find the pattern"
    print("   ✓ Pattern found")

    # Device is hung - NO NEW LINES are added
    print("\n3. Device hung - no new serial output for 12 seconds...")
    print("   (no lines added to buffer)")

    # Second search - BUG: will NOT find it because no new lines!
    print("\n4. Second search_recent call (12 seconds later, polling again)...")
    print("   Expected: Should still find pattern in recent lines")
    print("   Bug: Won't find it because start_from_last=True only searches NEW lines")

    found = reader.search_recent(pattern, max_lines=15, regex=True)
    print(f"   Result: {found}")
    print(f"   _recent_read is now: {reader._recent_read} (total buffer: {len(reader._buffer)} lines)")

    assert found, (
        "Second search should STILL find the pattern in recent lines, "
        "but it returns False because search_recent uses start_from_last=True "
        "which only searches lines added SINCE the last call. "
        "Since the device is hung and not producing new output, "
        "there are no new lines to search!"
    )
    print("   ✓ Pattern found on second search")

    print("\n" + "=" * 60)
    print("🎉 Repeated search test passed!")
    print()


if __name__ == "__main__":
    test_buffer_api()
    test_ansi_escape_filtering()
    test_search_recent_with_many_new_lines()
    test_shutdown_hang_pattern_matching()
    test_repeated_search_without_new_lines()
