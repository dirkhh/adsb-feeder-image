import socket
import subprocess
import threading
import time
from time import sleep
from typing import Callable, Optional

import requests

from .data import Data
from .paths import ADSB_SCRIPTS_DIR, DOCKER_COMPOSE_ADSB_SCRIPT, DOCKER_COMPOSE_START_SCRIPT
from .util import print_err, run_shell_captured


class Lock:
    """Lock wrapper to prevent system modifications while pending changes are being made."""

    def __init__(self) -> None:
        self.lock = threading.Lock()

    def acquire(self, blocking: bool = True, timeout: float = -1.0) -> bool:
        """Acquire the lock."""
        return self.lock.acquire(blocking=blocking, timeout=timeout)

    def release(self) -> None:
        """Release the lock."""
        return self.lock.release()

    def locked(self) -> bool:
        """Check if the lock is currently held."""
        return self.lock.locked()

    # make sure we can use "with Lock() as lock:"

    def __enter__(self) -> "Lock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


class Restart:
    """Manage system restart operations with locking."""

    def __init__(self, lock: Lock) -> None:
        self.lock = lock

    def bg_run(self, cmdline: Optional[str] = None, func: Optional[Callable] = None, silent: bool = False) -> bool:
        """
        Run a command or function in background with lock protection.

        Args:
            cmdline: Shell command to execute
            func: Python function to call
            silent: If True, capture command output

        Returns:
            True if started successfully, False if lock couldn't be acquired
        """
        if not cmdline and not func:
            print_err(f"WARNING: bg_run called without something to do")
            return False

        gotLock = self.lock.acquire(blocking=False)

        if not gotLock:
            # we could not acquire the lock
            print_err(f"restart locked, couldn't run: {cmdline}")
            return False

        # we have acquired the lock

        def do_restart() -> None:
            try:
                if cmdline:
                    print_err(f"Calling {cmdline}")
                    subprocess.run(
                        cmdline,
                        shell=True,
                        capture_output=silent,
                    )
                if func:
                    func()
            finally:
                self.lock.release()

        threading.Thread(target=do_restart).start()

        return True

    def wait_restart_done(self, timeout: float = -1.0) -> None:
        """Wait for restart operation to complete."""
        # acquire and release the lock immediately
        if self.lock.acquire(blocking=True, timeout=timeout):
            self.lock.release()

    @property
    def state(self) -> str:
        """Get current restart state ('busy' or 'done')."""
        if self.lock.locked():
            return "busy"
        return "done"

    @property
    def is_restarting(self) -> bool:
        """Check if a restart operation is in progress."""
        return self.lock.locked()


class System:
    """System operations for managing containers, network, and OS updates."""

    def __init__(self, data: Data) -> None:
        self._restart_lock = Lock()
        self._restart = Restart(self._restart_lock)
        self._d = data

        self.gateway_ips: list[str] | None = None

        self.containerCheckLock = threading.RLock()
        self.lastContainerCheck: float = 0.0
        self.dockerPsCache: dict[str, str] = dict()

    @property
    def restart(self) -> Restart:
        """Get the restart manager instance."""
        return self._restart

    def shutdown_action(self, action: str = "", delay: float = 0.0) -> None:
        if action == "shutdown":
            cmd = "shutdown now"
        elif action == "reboot":
            cmd = "reboot"
        else:
            print_err(f"unknown shutdown action: {action}")
            return

        print_err(f"shutdown action: {action}")

        # best effort: allow reboot / shutdown even if lock is held
        gotLock = self._restart.lock.acquire(blocking=False)

        def do_action():
            sleep(delay)
            subprocess.call(cmd, shell=True)
            # just in case the reboot doesn't work,
            # release the lock after 30 seconds:
            if gotLock:
                sleep(30)
                self._restart.lock.release()

        threading.Thread(target=do_action).start()

    def shutdown(self, delay=0.0) -> None:
        self.shutdown_action(action="shutdown", delay=delay)

    def reboot(self, delay=0.0) -> None:
        self.shutdown_action(action="reboot", delay=delay)

    def os_update(self) -> None:
        subprocess.call(f"systemd-run --wait -u adsb-feeder-update-os /bin/bash {ADSB_SCRIPTS_DIR}/update-os", shell=True)

    def check_dns(self) -> bool:
        """Check if DNS resolution is working."""
        try:
            responses = list(
                i[4][0]  # raw socket structure/internet protocol info/address
                for i in socket.getaddrinfo("adsb.im", 0)
                # if i[0] is socket.AddressFamily.AF_INET
                # and i[1] is socket.SocketKind.SOCK_RAW
            )
        except Exception:
            return False
        return responses != list()

    def is_ipv6_broken(self) -> bool:
        """Check if IPv6 connectivity is broken despite having an IPv6 address."""
        success, output = run_shell_captured(
            "ip -6 addr show scope global $(ip -j route get 1.2.3.4 | jq '.[0].dev' -r) | grep inet6 | grep -v 'inet6 f'",
            timeout=2,
        )
        if not success:
            # no global ipv6 addresses assigned, this means we don't have ipv6 so it can't be broken
            return False
        # we have at least one global ipv6 address, check if it works:
        success, output = run_shell_captured("curl -o /dev/null -6 https://google.com", timeout=2)

        if success:
            # it's working, so it's not broken
            return False

        # we have an ipv6 address but curl -6 isn't working
        return True

    def check_ip(self) -> tuple[Optional[str], int]:
        """
        Check external IP address.

        Returns:
            Tuple of (IP address or None, HTTP status code or error number)
        """
        requests.packages.urllib3.util.connection.HAS_IPV6 = False  # type: ignore[attr-defined]
        status = -1
        try:
            response = requests.get(
                "http://v4.ipv6-test.com/api/myip.php",
                headers={
                    "User-Agent": "Python3/requests/adsb.im",
                    "Accept": "text/plain",
                },
            )
        except (
            requests.HTTPError,
            requests.ConnectionError,
            requests.Timeout,
            requests.RequestException,
        ) as err:
            status = err.errno if err.errno else -1
        except Exception:
            status = -1
        else:
            return response.text, response.status_code
        return None, status

    def check_gpsd(self) -> bool:
        # gateway IP shouldn't change on a system, buffer it for the duration the program runs
        if self.gateway_ips:
            gateway_ips = self.gateway_ips
        else:
            # find host address on the docker network
            command = "docker exec adsb-setup-proxy ip route | mawk '/default/{ print($3) }'"
            success, output = run_shell_captured(
                command=command,
                timeout=5,
            )
            if success and len(output.strip()) > 4:
                self.gateway_ips = gateway_ips = [output.strip()]
            else:
                gateway_ips = ["172.17.0.1", "172.18.0.1"]
                print_err(f"ERROR: command: {command} failed with output: {output}")

        print_err(f"gpsd check: checking ips: {gateway_ips}")

        for ip in gateway_ips:
            # Create a TCP socket
            # print_err(f"Checking for gpsd: {ip}:2947")
            s = socket.socket()
            s.settimeout(2)
            try:
                s.connect((ip, 2947))
                print_err(f"Connected to gpsd on {ip}:2947")
                return True
            except socket.error:
                print_err(f"No gpsd on {ip}:2947 detected")
            finally:
                s.close()
        return False

    def list_containers(self) -> list[str]:
        """
        List all running Docker containers.

        Returns:
            List of container names
        """
        containers = []
        try:
            result = subprocess.run(
                ["docker", "ps", "--format='{{json .Names}}'"],
                capture_output=True,
                timeout=5,
            )
            output = result.stdout.decode("utf-8")
            for line in output.split("\n"):
                if line and line[1] == '"' and line[-2] == '"':
                    # the names show up as '"ultrafeeder"'
                    containers.append(line[2:-2])
        except subprocess.SubprocessError as e:
            print_err(f"docker ps failed {e}")
        return containers

    def restart_containers(self, containers: list[str]) -> None:
        """Restart specified Docker containers."""
        print_err(f"restarting {containers}")
        try:
            subprocess.run([str(DOCKER_COMPOSE_ADSB_SCRIPT), "restart"] + containers)
        except Exception:
            print_err("docker compose restart failed")

    def recreate_containers(self, containers: list[str]) -> None:
        """Recreate specified Docker containers (down + up --force-recreate)."""
        print_err(f"recreating {containers}")
        try:
            subprocess.run([str(DOCKER_COMPOSE_ADSB_SCRIPT), "down", "--remove-orphans", "-t", "30"] + containers)
            subprocess.run([str(DOCKER_COMPOSE_ADSB_SCRIPT), "up", "-d", "--force-recreate", "--remove-orphans"] + containers)
        except Exception:
            print_err("docker compose recreate failed")

    def stop_containers(self, containers: list[str]) -> None:
        """Stop specified Docker containers."""
        print_err(f"stopping {containers}")
        try:
            subprocess.run([str(DOCKER_COMPOSE_ADSB_SCRIPT), "down", "-t", "30"] + containers)
        except Exception:
            print_err(f"docker compose down {containers} failed")

    def start_containers(self) -> None:
        """Start all Docker containers."""
        print_err("starting all containers")
        try:
            subprocess.run([str(DOCKER_COMPOSE_START_SCRIPT)])
        except Exception:
            print_err("docker compose start failed")

    def refreshDockerPs(self) -> None:
        """Refresh the Docker container status cache."""
        with self.containerCheckLock:
            now = time.time()
            if now - self.lastContainerCheck < 10:
                # still fresh, do nothing
                return

            self.lastContainerCheck = now
            self.dockerPsCache = dict()
            cmdline = "docker ps --filter status=running --format '{{.Names}};{{.Status}}'"
            success, output = run_shell_captured(cmdline, timeout=5)
            if not success:
                print_err(f"Error: cmdline: {cmdline} output: {output}")
                return

            for line in output.split("\n"):
                if ";" in line:
                    name, status = line.split(";")
                    self.dockerPsCache[name] = status

    def getContainerStatus(self, name: str) -> str:
        """
        Get the status of a Docker container.

        Args:
            name: Container name

        Returns:
            Status string: 'down', 'up', or 'up for N' (seconds)
        """
        with self.containerCheckLock:

            self.refreshDockerPs()

            status = self.dockerPsCache.get(name)
            # print_err(f"{name}: {status}")
            if not status:
                # assume down
                return "down"

            if not status.startswith("Up"):
                return "down"

            if status == "Up Less than a second":
                return "up for 0"
            if status == "Up 1 second":
                return "up for 1"

            if "seconds" in status:
                try:
                    up, number, unit = status.split(" ")
                    # container up for some number of seconds, return how long it's been up
                    return f"up for {int(number)}"
                except Exception:
                    print_err(f"issue parsing container status: {status}")

            return "up"
