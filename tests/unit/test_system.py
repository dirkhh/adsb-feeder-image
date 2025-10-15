"""
Tests for utils.system module
"""
import socket
import subprocess
import threading
import time
from unittest.mock import patch, MagicMock, call, PropertyMock

import pytest
import requests

from utils.system import Lock, Restart, System
from utils.data import Data


class TestLock:
    """Test Lock class"""

    def test_lock_initialization(self):
        """Test Lock is properly initialized"""
        lock = Lock()
        # Check that lock has the expected methods (Lock() returns _thread.lock)
        assert hasattr(lock.lock, 'acquire')
        assert hasattr(lock.lock, 'release')
        assert not lock.locked()

    def test_lock_acquire_release_basic(self):
        """Test basic lock acquire and release"""
        lock = Lock()

        # Should be able to acquire lock
        assert lock.acquire()
        assert lock.locked()

        # Release lock
        lock.release()
        assert not lock.locked()

    def test_lock_acquire_blocking(self):
        """Test lock acquire with blocking parameter"""
        lock = Lock()

        # Acquire with blocking=True
        assert lock.acquire(blocking=True)
        assert lock.locked()

        # Try to acquire again without blocking - should fail
        assert not lock.acquire(blocking=False)

        lock.release()

    def test_lock_acquire_timeout(self):
        """Test lock acquire with timeout"""
        lock = Lock()
        lock.acquire()

        # Try to acquire with timeout - should fail and return False
        result = lock.acquire(blocking=True, timeout=0.1)
        assert not result

        lock.release()

    def test_lock_context_manager(self):
        """Test Lock works as context manager"""
        lock = Lock()

        with lock:
            assert lock.locked()

        # Should be released after exiting context
        assert not lock.locked()

    def test_lock_concurrent_access(self):
        """Test lock prevents concurrent access"""
        lock = Lock()
        results = []

        def worker(worker_id):
            if lock.acquire(blocking=True, timeout=1.0):
                results.append(f"start-{worker_id}")
                time.sleep(0.1)
                results.append(f"end-{worker_id}")
                lock.release()

        # Start two threads
        t1 = threading.Thread(target=worker, args=(1,))
        t2 = threading.Thread(target=worker, args=(2,))

        t1.start()
        t2.start()

        t1.join()
        t2.join()

        # Both threads should complete
        assert len(results) == 4
        # One thread should complete fully before the other starts
        assert results[0].startswith("start")
        assert results[1].startswith("end")


class TestRestart:
    """Test Restart class"""

    def test_restart_initialization(self):
        """Test Restart is properly initialized"""
        lock = Lock()
        restart = Restart(lock)

        assert restart.lock is lock
        assert restart.state == "done"
        assert not restart.is_restarting

    def test_restart_state_property(self):
        """Test restart state property reflects lock state"""
        lock = Lock()
        restart = Restart(lock)

        assert restart.state == "done"

        lock.acquire()
        assert restart.state == "busy"

        lock.release()
        assert restart.state == "done"

    def test_restart_is_restarting_property(self):
        """Test is_restarting property"""
        lock = Lock()
        restart = Restart(lock)

        assert not restart.is_restarting

        lock.acquire()
        assert restart.is_restarting

        lock.release()
        assert not restart.is_restarting

    @patch('utils.system.print_err')
    def test_bg_run_no_command_or_func(self, mock_print_err):
        """Test bg_run with neither command nor function"""
        lock = Lock()
        restart = Restart(lock)

        result = restart.bg_run()

        assert not result
        assert not lock.locked()
        mock_print_err.assert_called_once()
        assert "WARNING" in mock_print_err.call_args[0][0]

    @patch('subprocess.run')
    @patch('utils.system.print_err')
    def test_bg_run_with_command(self, mock_print_err, mock_subprocess):
        """Test bg_run executes command in background"""
        lock = Lock()
        restart = Restart(lock)

        result = restart.bg_run(cmdline="echo test")

        # Should return True and acquire lock
        assert result

        # Wait for background thread to complete
        restart.wait_restart_done(timeout=2.0)

        # Subprocess should have been called
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args
        assert args[0][0] == "echo test"
        assert args[1]['shell'] is True

        # Lock should be released after completion
        assert not lock.locked()

    @patch('utils.system.print_err')
    def test_bg_run_with_function(self, mock_print_err):
        """Test bg_run executes function in background"""
        lock = Lock()
        restart = Restart(lock)

        executed = []

        def test_func():
            executed.append(True)

        result = restart.bg_run(func=test_func)

        assert result

        # Wait for background thread
        restart.wait_restart_done(timeout=2.0)

        # Function should have been executed
        assert executed == [True]
        assert not lock.locked()

    @patch('subprocess.run')
    @patch('utils.system.print_err')
    def test_bg_run_with_both_command_and_func(self, mock_print_err, mock_subprocess):
        """Test bg_run executes both command and function"""
        lock = Lock()
        restart = Restart(lock)

        executed = []

        def test_func():
            executed.append(True)

        result = restart.bg_run(cmdline="echo test", func=test_func)

        assert result
        restart.wait_restart_done(timeout=2.0)

        # Both should have been called
        mock_subprocess.assert_called_once()
        assert executed == [True]

    @patch('utils.system.print_err')
    def test_bg_run_lock_contention(self, mock_print_err):
        """Test bg_run fails when lock is already held"""
        lock = Lock()
        restart = Restart(lock)

        # Acquire lock first
        lock.acquire()

        result = restart.bg_run(cmdline="echo test")

        # Should fail because lock is held
        assert not result
        mock_print_err.assert_called()
        assert "restart locked" in mock_print_err.call_args[0][0]

        lock.release()

    @patch('subprocess.run')
    def test_bg_run_silent_mode(self, mock_subprocess):
        """Test bg_run with silent=True captures output"""
        lock = Lock()
        restart = Restart(lock)

        restart.bg_run(cmdline="echo test", silent=True)
        restart.wait_restart_done(timeout=2.0)

        # Should capture output when silent=True
        args = mock_subprocess.call_args
        assert args[1]['capture_output'] is True

    @patch('subprocess.run')
    def test_bg_run_not_silent_mode(self, mock_subprocess):
        """Test bg_run with silent=False does not capture output"""
        lock = Lock()
        restart = Restart(lock)

        restart.bg_run(cmdline="echo test", silent=False)
        restart.wait_restart_done(timeout=2.0)

        # Should not capture output when silent=False
        args = mock_subprocess.call_args
        assert args[1]['capture_output'] is False

    def test_wait_restart_done_timeout(self):
        """Test wait_restart_done with timeout"""
        lock = Lock()
        restart = Restart(lock)

        # Acquire lock in another thread
        lock.acquire()

        # wait_restart_done should timeout and return
        start = time.time()
        restart.wait_restart_done(timeout=0.5)
        elapsed = time.time() - start

        # Should have timed out around 0.5 seconds
        assert 0.4 < elapsed < 0.7

        lock.release()


class TestSystemShutdown:
    """Test System shutdown and reboot functionality"""

    def test_system_initialization(self):
        """Test System is properly initialized"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        assert system._d is mock_data
        assert isinstance(system._restart_lock, Lock)
        assert isinstance(system._restart, Restart)
        assert system.gateway_ips is None
        # RLock() returns _thread.RLock, so check for methods instead
        assert hasattr(system.containerCheckLock, 'acquire')
        assert hasattr(system.containerCheckLock, 'release')
        assert system.lastContainerCheck == 0.0
        assert system.dockerPsCache == {}

    @patch('utils.data.Data')
    def test_restart_property(self, mock_data):
        """Test restart property returns Restart instance"""
        system = System(mock_data)

        assert isinstance(system.restart, Restart)
        assert system.restart is system._restart

    @patch('subprocess.call')
    @patch('utils.system.print_err')
    @patch('utils.data.Data')
    def test_shutdown_action_shutdown(self, mock_data, mock_print_err, mock_subprocess):
        """Test shutdown_action with shutdown command"""
        system = System(mock_data)

        system.shutdown_action(action="shutdown", delay=0.0)

        # Wait for background thread
        time.sleep(0.2)

        mock_subprocess.assert_called()
        args = mock_subprocess.call_args[0]
        assert args[0] == "shutdown now"

    @patch('subprocess.call')
    @patch('utils.system.print_err')
    @patch('utils.data.Data')
    def test_shutdown_action_reboot(self, mock_data, mock_print_err, mock_subprocess):
        """Test shutdown_action with reboot command"""
        system = System(mock_data)

        system.shutdown_action(action="reboot", delay=0.0)

        # Wait for background thread
        time.sleep(0.2)

        mock_subprocess.assert_called()
        args = mock_subprocess.call_args[0]
        assert args[0] == "reboot"

    @patch('utils.system.print_err')
    @patch('utils.data.Data')
    def test_shutdown_action_invalid(self, mock_data, mock_print_err):
        """Test shutdown_action with invalid action"""
        system = System(mock_data)

        system.shutdown_action(action="invalid")

        mock_print_err.assert_called()
        assert "unknown shutdown action" in mock_print_err.call_args[0][0]

    @patch('subprocess.call')
    @patch('utils.data.Data')
    def test_shutdown_calls_shutdown_action(self, mock_data, mock_subprocess):
        """Test shutdown method calls shutdown_action"""
        system = System(mock_data)

        system.shutdown(delay=0.5)

        # Wait for background thread
        time.sleep(0.8)

        mock_subprocess.assert_called()
        args = mock_subprocess.call_args[0]
        assert args[0] == "shutdown now"

    @patch('subprocess.call')
    @patch('utils.data.Data')
    def test_reboot_calls_shutdown_action(self, mock_data, mock_subprocess):
        """Test reboot method calls shutdown_action"""
        system = System(mock_data)

        system.reboot(delay=0.5)

        # Wait for background thread
        time.sleep(0.8)

        mock_subprocess.assert_called()
        args = mock_subprocess.call_args[0]
        assert args[0] == "reboot"

    @patch('subprocess.call')
    @patch('utils.data.Data')
    def test_os_update(self, mock_data, mock_subprocess):
        """Test os_update runs update script"""
        system = System(mock_data)

        system.os_update()

        mock_subprocess.assert_called_once()
        # Verify the command contains the update script
        cmd = mock_subprocess.call_args[0][0]
        assert "systemd-run" in cmd
        assert "update-os" in cmd
        assert mock_subprocess.call_args[1]['shell'] is True


class TestSystemNetwork:
    """Test System network-related functionality"""

    @patch('socket.getaddrinfo')
    @patch('utils.data.Data')
    def test_check_dns_success(self, mock_data, mock_getaddrinfo):
        """Test check_dns with successful resolution"""
        system = System(mock_data)

        # Mock successful DNS resolution
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('104.21.32.160', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('172.67.150.229', 0)),
        ]

        result = system.check_dns()

        assert result is True
        mock_getaddrinfo.assert_called_once_with("adsb.im", 0)

    @patch('socket.getaddrinfo')
    @patch('utils.data.Data')
    def test_check_dns_failure(self, mock_data, mock_getaddrinfo):
        """Test check_dns with failed resolution"""
        system = System(mock_data)

        # Mock DNS failure
        mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")

        result = system.check_dns()

        assert result is False

    @patch('socket.getaddrinfo')
    @patch('utils.data.Data')
    def test_check_dns_empty_response(self, mock_data, mock_getaddrinfo):
        """Test check_dns with empty response"""
        system = System(mock_data)

        mock_getaddrinfo.return_value = []

        result = system.check_dns()

        assert result is False

    @patch('utils.system.run_shell_captured')
    def test_is_ipv6_broken_no_ipv6(self, mock_run_shell):
        """Test is_ipv6_broken when no IPv6 addresses exist"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        # Mock: no global IPv6 addresses
        mock_run_shell.return_value = (False, "")

        result = system.is_ipv6_broken()

        assert result is False

    @patch('utils.system.run_shell_captured')
    def test_is_ipv6_broken_working_ipv6(self, mock_run_shell):
        """Test is_ipv6_broken when IPv6 is working"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        # Mock: has IPv6 address and curl succeeds
        mock_run_shell.side_effect = [
            (True, "inet6 2001:db8::1"),  # Has global IPv6
            (True, ""),  # curl -6 succeeds
        ]

        result = system.is_ipv6_broken()

        assert result is False

    @patch('utils.system.run_shell_captured')
    def test_is_ipv6_broken_broken_ipv6(self, mock_run_shell):
        """Test is_ipv6_broken when IPv6 is broken"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        # Mock: has IPv6 address but curl fails
        mock_run_shell.side_effect = [
            (True, "inet6 2001:db8::1"),  # Has global IPv6
            (False, "curl: (7) Failed to connect"),  # curl -6 fails
        ]

        result = system.is_ipv6_broken()

        assert result is True

    @patch('requests.get')
    @patch('utils.data.Data')
    def test_check_ip_success(self, mock_data, mock_requests):
        """Test check_ip with successful API call"""
        system = System(mock_data)

        # Mock successful response
        mock_response = MagicMock()
        mock_response.text = "203.0.113.42"
        mock_response.status_code = 200
        mock_requests.return_value = mock_response

        ip, status = system.check_ip()

        assert ip == "203.0.113.42"
        assert status == 200

    @patch('requests.get')
    @patch('utils.data.Data')
    def test_check_ip_connection_error(self, mock_data, mock_requests):
        """Test check_ip with connection error"""
        system = System(mock_data)

        # Mock connection error
        error = requests.ConnectionError()
        error.errno = 111
        mock_requests.side_effect = error

        ip, status = system.check_ip()

        assert ip is None
        assert status == 111

    @patch('requests.get')
    @patch('utils.data.Data')
    def test_check_ip_timeout(self, mock_data, mock_requests):
        """Test check_ip with timeout"""
        system = System(mock_data)

        # Mock timeout
        error = requests.Timeout()
        error.errno = None
        mock_requests.side_effect = error

        ip, status = system.check_ip()

        assert ip is None
        assert status == -1

    @patch('requests.get')
    @patch('utils.data.Data')
    def test_check_ip_generic_exception(self, mock_data, mock_requests):
        """Test check_ip with generic exception"""
        system = System(mock_data)

        mock_requests.side_effect = Exception("Unknown error")

        ip, status = system.check_ip()

        assert ip is None
        assert status == -1

    @patch('socket.socket')
    @patch('utils.system.run_shell_captured')
    def test_check_gpsd_success(self, mock_run_shell, mock_socket_class):
        """Test check_gpsd with successful connection"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        # Mock docker command to get gateway IP
        mock_run_shell.return_value = (True, "172.17.0.1")

        # Mock socket connection success
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        result = system.check_gpsd()

        assert result is True
        mock_socket.connect.assert_called_once_with(("172.17.0.1", 2947))

    @patch('socket.socket')
    @patch('utils.system.run_shell_captured')
    def test_check_gpsd_connection_failure(self, mock_run_shell, mock_socket_class):
        """Test check_gpsd with connection failure"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (True, "172.17.0.1")

        # Mock socket connection failure
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = socket.error("Connection refused")
        mock_socket_class.return_value = mock_socket

        result = system.check_gpsd()

        assert result is False

    @patch('socket.socket')
    @patch('utils.system.run_shell_captured')
    @patch('utils.system.print_err')
    def test_check_gpsd_fallback_ips(self, mock_print_err, mock_run_shell, mock_socket_class):
        """Test check_gpsd falls back to default IPs"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        # Mock docker command failure
        mock_run_shell.return_value = (False, "error")

        # Mock socket connection success on second IP
        mock_socket = MagicMock()
        mock_socket.connect.side_effect = [
            socket.error("Connection refused"),  # First IP fails
            None,  # Second IP succeeds
        ]
        mock_socket_class.return_value = mock_socket

        result = system.check_gpsd()

        # Should try default IPs
        assert result is True
        assert mock_socket.connect.call_count == 2

    @patch('socket.socket')
    @patch('utils.system.run_shell_captured')
    def test_check_gpsd_caches_gateway_ips(self, mock_run_shell, mock_socket_class):
        """Test check_gpsd caches gateway IPs"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (True, "172.17.0.1")
        mock_socket = MagicMock()
        mock_socket_class.return_value = mock_socket

        # First call
        system.check_gpsd()
        assert system.gateway_ips == ["172.17.0.1"]

        # Second call should use cached IPs
        mock_run_shell.reset_mock()
        system.check_gpsd()

        # Should not run the docker command again
        mock_run_shell.assert_not_called()


class TestSystemDocker:
    """Test System Docker-related functionality"""

    @patch('subprocess.run')
    @patch('utils.data.Data')
    def test_list_containers_success(self, mock_data, mock_subprocess):
        """Test list_containers with successful docker ps"""
        system = System(mock_data)

        # Mock docker ps output
        mock_result = MagicMock()
        mock_result.stdout = b'\'\"ultrafeeder\"\'\n\'\"piaware\"\'\n\'\"fr24\"\'\n'
        mock_subprocess.return_value = mock_result

        containers = system.list_containers()

        assert containers == ["ultrafeeder", "piaware", "fr24"]

    @patch('subprocess.run')
    @patch('utils.data.Data')
    def test_list_containers_empty(self, mock_data, mock_subprocess):
        """Test list_containers with no containers"""
        system = System(mock_data)

        mock_result = MagicMock()
        mock_result.stdout = b''
        mock_subprocess.return_value = mock_result

        containers = system.list_containers()

        assert containers == []

    @patch('subprocess.run')
    @patch('utils.system.print_err')
    @patch('utils.data.Data')
    def test_list_containers_timeout(self, mock_data, mock_print_err, mock_subprocess):
        """Test list_containers with subprocess timeout"""
        system = System(mock_data)

        mock_subprocess.side_effect = subprocess.TimeoutExpired("docker", 5)

        containers = system.list_containers()

        assert containers == []
        mock_print_err.assert_called()

    @patch('subprocess.run')
    @patch('utils.data.Data')
    def test_restart_containers(self, mock_data, mock_subprocess):
        """Test restart_containers"""
        system = System(mock_data)

        system.restart_containers(["ultrafeeder", "piaware"])

        mock_subprocess.assert_called_once()
        # Verify command includes restart and container names
        args = mock_subprocess.call_args[0][0]
        assert "restart" in args
        assert "ultrafeeder" in args
        assert "piaware" in args

    @patch('subprocess.run')
    @patch('utils.system.print_err')
    @patch('utils.data.Data')
    def test_restart_containers_failure(self, mock_data, mock_print_err, mock_subprocess):
        """Test restart_containers with failure"""
        system = System(mock_data)

        mock_subprocess.side_effect = Exception("Docker error")

        system.restart_containers(["ultrafeeder"])

        mock_print_err.assert_called()
        assert "restart failed" in mock_print_err.call_args[0][0]

    @patch('subprocess.run')
    @patch('utils.data.Data')
    def test_recreate_containers(self, mock_data, mock_subprocess):
        """Test recreate_containers"""
        system = System(mock_data)

        system.recreate_containers(["ultrafeeder"])

        # Should call both down and up
        assert mock_subprocess.call_count == 2

        # First call should be down
        down_call = mock_subprocess.call_args_list[0][0][0]
        assert "down" in down_call
        assert "ultrafeeder" in down_call

        # Second call should be up
        up_call = mock_subprocess.call_args_list[1][0][0]
        assert "up" in up_call
        assert "--force-recreate" in up_call

    @patch('subprocess.run')
    @patch('utils.data.Data')
    def test_stop_containers(self, mock_data, mock_subprocess):
        """Test stop_containers"""
        system = System(mock_data)

        system.stop_containers(["ultrafeeder", "piaware"])

        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0][0]
        assert "down" in args
        assert "ultrafeeder" in args
        assert "piaware" in args

    @patch('subprocess.run')
    @patch('utils.data.Data')
    def test_start_containers(self, mock_data, mock_subprocess):
        """Test start_containers"""
        system = System(mock_data)

        system.start_containers()

        mock_subprocess.assert_called_once()

    @patch('utils.system.run_shell_captured')
    def test_refreshDockerPs_success(self, mock_run_shell):
        """Test refreshDockerPs updates cache"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (
            True,
            "ultrafeeder;Up 2 hours\npiaware;Up 30 minutes\nfr24;Up Less than a second"
        )

        system.refreshDockerPs()

        assert system.dockerPsCache == {
            "ultrafeeder": "Up 2 hours",
            "piaware": "Up 30 minutes",
            "fr24": "Up Less than a second"
        }

    @patch('utils.system.run_shell_captured')
    def test_refreshDockerPs_caching(self, mock_run_shell):
        """Test refreshDockerPs caches for 10 seconds"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (True, "ultrafeeder;Up 2 hours")

        # First call
        system.refreshDockerPs()
        assert mock_run_shell.call_count == 1

        # Immediate second call should use cache
        system.refreshDockerPs()
        assert mock_run_shell.call_count == 1  # Not called again

        # Simulate time passing
        system.lastContainerCheck = time.time() - 11

        # Third call should refresh
        system.refreshDockerPs()
        assert mock_run_shell.call_count == 2

    @patch('utils.system.run_shell_captured')
    def test_getContainerStatus_down(self, mock_run_shell):
        """Test getContainerStatus for down container"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (True, "")

        status = system.getContainerStatus("ultrafeeder")

        assert status == "down"

    @patch('utils.system.run_shell_captured')
    def test_getContainerStatus_up(self, mock_run_shell):
        """Test getContainerStatus for up container"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (True, "ultrafeeder;Up 2 hours")

        status = system.getContainerStatus("ultrafeeder")

        assert status == "up"

    @patch('utils.system.run_shell_captured')
    def test_getContainerStatus_up_for_seconds(self, mock_run_shell):
        """Test getContainerStatus parsing uptime in seconds"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        # Test various second formats
        test_cases = [
            ("ultrafeeder;Up Less than a second", "up for 0"),
            ("ultrafeeder;Up 1 second", "up for 1"),
            ("ultrafeeder;Up 5 seconds", "up for 5"),
            ("ultrafeeder;Up 42 seconds", "up for 42"),
        ]

        for docker_output, expected_status in test_cases:
            system.lastContainerCheck = 0  # Reset cache
            mock_run_shell.return_value = (True, docker_output)
            status = system.getContainerStatus("ultrafeeder")
            assert status == expected_status, f"Failed for {docker_output}"

    @patch('utils.system.run_shell_captured')
    def test_getContainerStatus_not_up(self, mock_run_shell):
        """Test getContainerStatus for container not in Up state"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        mock_run_shell.return_value = (True, "ultrafeeder;Restarting")

        status = system.getContainerStatus("ultrafeeder")

        assert status == "down"


class TestSystemThreadSafety:
    """Test System thread safety"""

    @patch('utils.system.run_shell_captured')
    def test_concurrent_docker_ps_refresh(self, mock_run_shell):
        """Test concurrent refreshDockerPs calls are thread-safe"""
        mock_data = MagicMock(spec=Data)
        system = System(mock_data)

        call_count = [0]

        def mock_run_shell_with_delay(*args, **kwargs):
            call_count[0] += 1
            time.sleep(0.1)  # Simulate slow docker ps
            return (True, "ultrafeeder;Up 1 hour")

        mock_run_shell.side_effect = mock_run_shell_with_delay

        # Run multiple concurrent refreshes
        threads = []
        for _ in range(5):
            t = threading.Thread(target=system.refreshDockerPs)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # With caching and thread safety, should only call once or twice
        # (not 5 times due to the lock)
        assert call_count[0] <= 2
