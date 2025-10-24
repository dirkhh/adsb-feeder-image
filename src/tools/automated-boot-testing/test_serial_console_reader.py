#!/usr/bin/env python3
"""
Unit tests for SerialConsoleReader

Tests the API without requiring actual serial hardware.
"""

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
    matches = reader.search_recent("iSCSI", max_lines=100)
    print(f"   Found {len(matches)} lines containing 'iSCSI':")
    for line in matches:
        print(f"     - {line}")
    assert len(matches) == 2, "Should find 2 lines with 'iSCSI'"
    print("   ✓ search_recent() string search working")

    # Test search_recent - regex
    print("\n4. Testing search_recent() with regex...")
    matches = reader.search_recent(r"DietPi-Boot: Phase \d", max_lines=100, regex=True)
    print(f"   Found {len(matches)} lines matching regex:")
    for line in matches:
        print(f"     - {line}")
    assert len(matches) == 2, "Should find 2 DietPi boot phase lines"
    print("   ✓ search_recent() regex search working")

    # Test search_recent - USB devices
    print("\n5. Testing search for USB devices...")
    matches = reader.search_recent(r"USB \d+-\d+", max_lines=100, regex=True)
    print(f"   Found {len(matches)} USB device messages:")
    for line in matches:
        print(f"     - {line}")
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
    assert "DietPi login:" in matching_line, "Should match correct line"
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

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".log") as f:
        temp_file = f.name

    reader._buffer.clear()
    reader._buffer.append("Line 1")
    reader._buffer.append("Line 2")
    reader._buffer.append("Line 3")

    success = reader.save_to_file(temp_file)
    assert success, "Should save successfully"

    # Verify file contents
    with open(temp_file, "r") as f:
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


if __name__ == "__main__":
    test_buffer_api()
