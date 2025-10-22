import re
import shlex
import subprocess
from typing import Any, Optional

from flask import flash

from .paths import ADSB_BASE_DIR, ADSB_RB_DIR
from .system import System
from .util import is_email, make_int, print_err, report_issue


class Aggregator:
    """Base class for ADS-B aggregator integrations."""

    def __init__(
        self,
        name: str,
        system: System,
        tags: list[str] = [],
    ) -> None:
        self._name = name
        self._tags = tags
        self._system = system
        self._d = system._d
        self._idx = 0

    @property
    def name(self) -> str:
        """Get aggregator name."""
        return self._name

    @property
    def tags(self) -> list[str]:
        """Get aggregator tags."""
        return self._tags

    @property
    def _key_tags(self) -> list[str]:
        """Get tags for API key lookup."""
        return ["key"] + self.tags

    @property
    def _enabled_tags(self) -> list[str]:
        """Get tags for enabled status lookup."""
        return ["is_enabled", "other_aggregator"] + self.tags

    @property
    def lat(self) -> Any:
        """Get latitude from configuration."""
        return self._d.env_by_tags("lat").list_get(self._idx)

    @property
    def lon(self) -> Any:
        """Get longitude from configuration."""
        return self._d.env_by_tags("lon").list_get(self._idx)

    @property
    def alt(self) -> Any:
        """Get altitude from configuration."""
        return self._d.env_by_tags("alt").list_get(self._idx)

    @property
    def alt_ft(self) -> int:
        """Get altitude in feet."""
        return int(int(self.alt) / 0.308)

    @property
    def container(self) -> str:
        """Get Docker container name."""
        # we know that the container Env is always a string
        return self._d.env_by_tags(self.tags + ["container"]).valuestr

    @property
    def is_enabled(self, idx: int = 0) -> Any:
        """Check if aggregator is enabled."""
        return self._d.env_by_tags(self._enabled_tags).list_get(self._idx)

    def _activate(self, user_input: str, idx: int) -> bool:
        """Activate aggregator with user credentials (to be implemented by subclasses)."""
        raise NotImplementedError

    def _deactivate(self) -> bool:
        """Deactivate aggregator (to be implemented by subclasses)."""
        raise NotImplementedError

    def _download_docker_container(self, container: str) -> bool:
        print_err(f"download_docker_container {container}")
        cmdline = f"docker pull {container}"
        try:
            subprocess.run(cmdline, timeout=180.0, shell=True)
        except subprocess.TimeoutExpired:
            return False
        return True

    def _docker_run_with_timeout(self, cmdline: str, timeout: float) -> str:
        """Run Docker container with timeout and return output."""

        def force_remove_container(name: str) -> None:
            try:
                subprocess.run(
                    f"docker rm -f {name}",
                    timeout=15,
                    shell=True,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired as exc2:
                print_err(f"failed to remove the container {name} stderr: {str(exc2.stdout)} / stdout: {str(exc2.stderr)}")

        # let's make sure the container isn't still there, if it is the docker run won't work
        force_remove_container("temp_container")
        output = ""
        try:
            result = subprocess.run(
                f"docker run --name temp_container {cmdline}",
                timeout=timeout,
                shell=True,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired as exc:
            # for several of these containers "timeout" is actually the expected behavior;
            # they don't stop on their own. So just grab the output and kill the container
            output = exc.stdout.decode() if exc.stdout else ""
            print_err(f"docker run {cmdline} received a timeout error after {timeout} with output {output}")

            force_remove_container("temp_container")
        except subprocess.SubprocessError as exc:
            print_err(f"docker run {cmdline} ended with an exception {exc}")
        else:
            output = result.stdout if result.stdout else ""
            print_err(f"docker run {cmdline} completed with output {output}")
        return output

    # the default case is straight forward. Remember the key and enable the aggregator
    def _simple_activate(self, user_input: str, idx: int = 0) -> bool:
        """
        Simple activation: store user key and enable aggregator.

        Args:
            user_input: API key or user credential
            idx: Index for multi-instance configurations

        Returns:
            True if activation successful, False otherwise
        """
        if not user_input:
            return False
        self._d.env_by_tags(self._key_tags).list_set(idx, user_input)
        self._d.env_by_tags(self._enabled_tags).list_set(idx, True)
        return True


class ADSBHub(Aggregator):
    """ADSBHub aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="ADSBHub",
            tags=["adsb_hub"],
            system=system,
        )

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        return self._simple_activate(user_input, idx)


class FlightRadar24(Aggregator):
    """FlightRadar24 aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="FlightRadar24",
            tags=["flightradar"],
            system=system,
        )

    def _request_fr24_sharing_key(self, email: str) -> Optional[str]:
        """Request FR24 sharing key with input validation to prevent command injection."""
        # Validate email format before using in command
        if not is_email(email):
            print_err(f"Invalid email format: {email}")
            flash("Invalid email format for FR24 signup")
            return None

        if not self._download_docker_container(self.container):
            report_issue("failed to download the FR24 docker image")
            return None

        lat = float(self.lat)
        lon = float(self.lon)

        if abs(lat) < 0.5 and abs(lon) < 0.5:
            # this is at null island, just fail for this
            report_issue("FR24 cannot handle 'null island'")
            return None

        # so this signup doesn't work for latitude / longitude <0.1, work around that by just setting longitude 0.11 in that case
        # we don't do FR24 mlat anyhow ... if people want to fix it they can do so on the fr24 homepage
        if abs(lat) < 0.11:
            lat = 0.11
        if abs(lon) < 0.11:
            lon = 0.11

        # Sanitize all inputs to prevent command injection
        safe_email = shlex.quote(email.lower())
        safe_lat = shlex.quote(str(lat))
        safe_lon = shlex.quote(str(lon))
        safe_alt = shlex.quote(str(self.alt_ft))
        safe_container = shlex.quote(self.container)

        adsb_signup_command = (
            f"docker run --entrypoint /bin/bash --rm "
            f"-e FEEDER_LAT={safe_lat} -e FEEDER_LONG={safe_lon} -e FEEDER_ALT_FT={safe_alt} "
            f"-e FR24_EMAIL={safe_email} {safe_container} "
            f'-c "apt update && apt install -y expect && $(cat handsoff_signup_expect.sh)"'
        )
        open(ADSB_BASE_DIR / "handsoff_signup.sh", "w").write(f"#!/bin/bash\n{adsb_signup_command}")
        try:
            output = subprocess.run(
                ["bash", str(ADSB_BASE_DIR / "handsoff_signup.sh")],
                cwd=str(ADSB_BASE_DIR),
                timeout=180.0,
                text=True,
                capture_output=True,
            ).stdout
        except subprocess.TimeoutExpired as exc:
            output = ""
            if exc.stdout:
                output += exc.stdout.decode()
            if exc.stderr:
                output += exc.stderr.decode()
            print_err(f"timeout running the FR24 signup script, output: {output}")
            flash("FR24 signup script timed out")
            return None

        sharing_key_match = re.search("Your sharing key \\(([a-zA-Z0-9]*)\\) has been", output)
        if not sharing_key_match:
            print_err(f"couldn't find a sharing key in the container output: {output}")
            flash("FR24: couldn't find a sharing key in server response")
            return None
        adsb_key = sharing_key_match.group(1)
        print_err(f"found adsb sharing key {adsb_key} in the container output")
        return adsb_key

    def _request_fr24_uat_sharing_key(self, email: str) -> Optional[str]:
        """Request FR24 UAT sharing key with input validation to prevent command injection."""
        # Validate email format before using in command
        if not is_email(email):
            print_err(f"Invalid email format: {email}")
            flash("Invalid email format for FR24 UAT signup")
            return None

        if not self._download_docker_container(self.container):
            report_issue("failed to download the FR24 docker image")
            return None

        # Sanitize all inputs to prevent command injection
        safe_email = shlex.quote(email)
        safe_lat = shlex.quote(str(self.lat))
        safe_lon = shlex.quote(str(self.lon))
        safe_alt = shlex.quote(str(self.alt_ft))
        safe_container = shlex.quote(self.container)

        uat_signup_command = (
            f"docker run --entrypoint /bin/bash --rm "
            f"-e FEEDER_LAT={safe_lat} -e FEEDER_LONG={safe_lon} -e FEEDER_ALT_FT={safe_alt} "
            f"-e FR24_EMAIL={safe_email} {safe_container} "
            f'-c "apt update && apt install -y expect && $(cat handsoff_signup_expect_uat.sh)"'
        )
        open(ADSB_BASE_DIR / "handsoff_signup_uat.sh", "w").write(f"#!/bin/bash\n{uat_signup_command}")
        try:
            output = subprocess.run(
                ["bash", str(ADSB_BASE_DIR / "handsoff_signup_uat.sh")],
                cwd=str(ADSB_BASE_DIR),
                timeout=180.0,
                text=True,
                capture_output=True,
            ).stdout
        except subprocess.TimeoutExpired as exc:
            output = ""
            if exc.stdout:
                output += exc.stdout.decode()
            if exc.stderr:
                output += exc.stderr.decode()
            print_err(f"timeout running the FR24 UAT signup script, output: {output}")
            flash("FR24 UAT signup script timed out")
            return None
        sharing_key_match = re.search("Your sharing key \\(([a-zA-Z0-9]*)\\) has been", output)
        if not sharing_key_match:
            print_err(f"couldn't find a UAT sharing key in the container output: {output}")
            flash("FR24: couldn't find a UAT sharing key in server response")
            return None
        uat_key = sharing_key_match.group(1)
        print_err(f"found uat sharing key {uat_key} in the container output")
        return uat_key

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        if not user_input:
            return False
        input_values = user_input.count("::")
        adsb_sharing_key: Optional[str] = None
        uat_sharing_key: Optional[str] = None
        if input_values > 1:
            return False
        elif input_values == 1:
            adsb_sharing_key, uat_sharing_key = user_input.split("::")
        else:
            adsb_sharing_key = user_input
            uat_sharing_key = None
        if not adsb_sharing_key and not uat_sharing_key:
            return False
        self._idx = make_int(idx)  # this way the properties work correctly
        print_err(f"FR_activate adsb |{adsb_sharing_key}| uat |{uat_sharing_key}| idx |{idx}|")

        if adsb_sharing_key and is_email(adsb_sharing_key):
            # that's an email address, so we are looking to get a sharing key
            adsb_sharing_key = self._request_fr24_sharing_key(adsb_sharing_key)
            print_err(f"got back sharing_key |{adsb_sharing_key}|")
        if adsb_sharing_key and not re.match("[0-9a-zA-Z]+", adsb_sharing_key):
            adsb_sharing_key = None
            report_issue("invalid FR24 sharing key")

        if uat_sharing_key and is_email(uat_sharing_key):
            # that's an email address, so we are looking to get a sharing key
            uat_sharing_key = self._request_fr24_uat_sharing_key(uat_sharing_key)
            print_err(f"got back uat_sharing_key |{uat_sharing_key}|")
        if uat_sharing_key and not re.match("[0-9a-zA-Z]+", uat_sharing_key):
            uat_sharing_key = None
            report_issue("invalid FR24 UAT sharing key")

        # overwrite email in config so that the container is not started with the email as sharing key if failed
        # otherwise just set sharing key as appropriate
        self._d.env_by_tags(["flightradar", "key"]).list_set(idx, adsb_sharing_key or "")
        self._d.env_by_tags(["flightradar_uat", "key"]).list_set(idx, uat_sharing_key or "")

        if adsb_sharing_key or uat_sharing_key:
            # we have at least one sharing key, let's just enable the container
            self._d.env_by_tags(self._enabled_tags).list_set(idx, True)
            return True
        else:
            self._d.env_by_tags(self._enabled_tags).list_set(idx, False)
            return False


class PlaneWatch(Aggregator):
    """PlaneWatch aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="PlaneWatch",
            tags=["planewatch"],
            system=system,
        )

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        return self._simple_activate(user_input, idx)


class FlightAware(Aggregator):
    """FlightAware aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="FlightAware",
            tags=["flightaware"],
            system=system,
        )

    def _request_fa_feeder_id(self) -> Optional[str]:
        if not self._download_docker_container(self.container):
            report_issue("failed to download the piaware docker image")
            return None

        cmdline = f"--rm {self.container}"
        output = self._docker_run_with_timeout(cmdline, 45.0)
        feeder_id_match = re.search(" feeder ID is ([-a-zA-Z0-9]*)", output)
        if feeder_id_match:
            return feeder_id_match.group(1)
        print_err(f"couldn't find a feeder ID in the container output: {output}")
        flash("FlightAware: couldn't find a feeder ID in server response")
        return None

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        self._idx = make_int(idx)
        feeder_id: Optional[str]
        if re.match("[0-9a-zA-Z]+", user_input):
            # that might be a valid key
            feeder_id = user_input
        else:
            feeder_id = self._request_fa_feeder_id()
            print_err(f"got back feeder_id |{feeder_id}|")
        if not feeder_id:
            return False

        self._d.env_by_tags(self._key_tags).list_set(idx, feeder_id)
        self._d.env_by_tags(self._enabled_tags).list_set(idx, True)
        return True


class RadarBox(Aggregator):
    """AirNav RadarBox aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="AirNav Radar",
            tags=["radarbox"],
            system=system,
        )

    def _request_rb_sharing_key(self, idx: int) -> Optional[str]:
        # we know that the container Env is always a string
        docker_image = self._d.env_by_tags(["radarbox", "container"]).valuestr

        if not self._download_docker_container(docker_image):
            report_issue("failed to download the AirNav Radar docker image")
            return None

        suffix = f"_{idx}" if idx else ""
        # make sure we correctly enable the hacks
        extra_env = f"-v {ADSB_RB_DIR}/cpuinfo{suffix}:/proc/cpuinfo "
        if self._d.env_by_tags("rbthermalhack").value != "":
            extra_env += f"-v {ADSB_RB_DIR}:/sys/class/thermal:ro "

        cmdline = (
            f"--rm -i --network adsb_im_bridge -e BEASTHOST=ultrafeeder -e LAT={self.lat} "
            f"-e LONG={self.lon} -e ALT={self.alt} {extra_env} {docker_image}"
        )
        output = self._docker_run_with_timeout(cmdline, 45.0)
        sharing_key_match = re.search("Your new key is ([a-zA-Z0-9]*)", output)
        if not sharing_key_match:
            print_err(f"couldn't find a sharing key in the container output: {output}")
            flash("AirNav Radar: couldn't find a sharing key in server response")
            return None

        return sharing_key_match.group(1)

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        self._idx = make_int(idx)
        sharing_key: Optional[str]
        if re.match("[0-9a-zA-Z]+", user_input):
            # that might be a valid key
            sharing_key = user_input
        else:
            # try to get a key
            sharing_key = self._request_rb_sharing_key(idx)
        if not sharing_key:
            return False

        self._d.env_by_tags(self._key_tags).list_set(idx, sharing_key)
        self._d.env_by_tags(self._enabled_tags).list_set(idx, True)
        return True


class OpenSky(Aggregator):
    """OpenSky Network aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="OpenSky Network",
            tags=["opensky"],
            system=system,
        )

    def _request_fr_serial(self, user: str) -> Optional[str]:
        # we know that the container Env is always a string
        docker_image = self._d.env_by_tags(["opensky", "container"]).valuestr

        if not self._download_docker_container(docker_image):
            report_issue("failed to download the OpenSky docker image")
            return None

        cmdline = (
            f"--rm -i --network adsb_im_bridge -e BEASTHOST=ultrafeeder -e LAT={self.lat} "
            f"-e LONG={self.lon} -e ALT={self.alt} -e OPENSKY_USERNAME={user} {docker_image}"
        )
        output = self._docker_run_with_timeout(cmdline, 60.0)
        serial_match = re.search("Got a new serial number: ([-a-zA-Z0-9]*)", output)
        if not serial_match:
            print_err(f"couldn't find a serial number in the container output: {output}")
            flash("OpenSky: couldn't find a serial number in server response")
            return None

        return serial_match.group(1)

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        self._idx = make_int(idx)
        serial, user = user_input.split("::")
        print_err(f"passed in {user_input} seeing user |{user}| and serial |{serial}|")
        if not user:
            print_err(f"missing user name for OpenSky")
            return False
        serial_value: Optional[str] = serial
        if not serial:
            print_err(f"need to request serial for OpenSky")
            serial_value = self._request_fr_serial(user)
            if not serial_value:
                print_err("failed to get OpenSky serial")
                return False
        self._d.env_by_tags(self.tags + ["user"]).list_set(idx, user)
        self._d.env_by_tags(self.tags + ["key"]).list_set(idx, serial_value)
        self._d.env_by_tags(self.tags + ["is_enabled"]).list_set(idx, True)
        return True


class RadarVirtuel(Aggregator):
    """RadarVirtuel aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="RadarVirtuel",
            tags=["radarvirtuel"],
            system=system,
        )

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        return self._simple_activate(user_input, idx)


class PlaneFinder(Aggregator):
    """PlaneFinder aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="PlaneFinder",
            tags=["planefinder"],
            system=system,
        )

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        return self._simple_activate(user_input, idx)


class Uk1090(Aggregator):
    """1090Mhz UK aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="1090Mhz UK",
            tags=["1090uk"],
            system=system,
        )

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        return self._simple_activate(user_input, idx)


class Sdrmap(Aggregator):
    """Sdrmap aggregator integration."""

    def __init__(self, system: System) -> None:
        super().__init__(
            name="sdrmap",
            tags=["sdrmap"],
            system=system,
        )

    def _activate(self, user_input: str, idx: int = 0) -> bool:
        self._idx = make_int(idx)
        password, user = user_input.split("::")
        print_err(f"passed in {user_input} seeing user |{user}| and password |{password}|")
        if not user:
            print_err(f"missing user name for sdrmap")
            return False
        if not password:
            print_err(f"missing password for sdrmap")
            return False
        self._d.env_by_tags(self.tags + ["user"]).list_set(idx, user)
        self._d.env_by_tags(self.tags + ["key"]).list_set(idx, password)
        self._d.env_by_tags(self.tags + ["is_enabled"]).list_set(idx, True)
        return True
