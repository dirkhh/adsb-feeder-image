import re
import sys
import subprocess

from .system import System


def print_err(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)


class Aggregator:
    def __init__(
        self,
        name: str,
        system: System,
        tags: list = None,
    ):
        self._name = name
        self._tags = tags
        self._system = system
        self._constants = system._constants

    @property
    def name(self):
        return self._name

    @property
    def tags(self):
        return self._tags

    @property
    def _key_tags(self):
        return ["key"] + self.tags

    @property
    def _enabled_tags(self):
        return ["is_enabled", "other_aggregator"] + self.tags

    @property
    def lat(self):
        return self._constants.envs["FEEDER_LAT"]

    @property
    def lng(self):
        return self._constants.envs["FEEDER_LONG"]

    @property
    def alt(self):
        return self._constants.envs["FEEDER_ALT_M"]

    @property
    def alt_ft(self):
        return int(int(self.alt) / 0.308)

    @property
    def container(self):
        return self._constants.env_by_tags(self.tags + ["container"]).value

    @property
    def is_enabled(self):
        return self._constants.env_by_tags(self._enabled_tags).value

    def _activate(self, user_input: str):
        raise NotImplementedError

    def _deactivate(self):
        raise NotImplementedError

    def _download_docker_container(self, container: str) -> bool:
        print_err(f"download_docker_container {container}")
        cmdline = f"docker pull {container}"
        try:
            result = subprocess.run(cmdline, timeout=180.0, shell=True)
        except subprocess.TimeoutExpired:
            return False
        return True

    def _docker_run_with_timeout(self, cmdline: str, timeout: float) -> str:
        try:
            result = subprocess.run(
                f"docker run {cmdline}", timeout=timeout, shell=True, capture_output=True
            )
        except subprocess.TimeoutExpired as exc:
            # for several of these containers "timeout" is actually the expected behavior;
            # they don't stop on their own. So just grab the output and kill the container
            output = str(exc.stdout)
            try:
                result = subprocess.run(
                    "docker rm -f temp_container",
                    timeout=10.0,
                    shell=True,
                    capture_output=True,
                )
            except subprocess.TimeoutExpired:
                print_err(
                    f"failed to remove the temp container {str(result.stdout)} / {str(result.stderr)}"
                )
        else:
            output = str(result.stdout)
        return output

    # the default case is straight forward. Remember the key and enable the aggregator
    def _simple_activate(self, user_input: str):
        if not user_input:
            return False
        self._constants.env_by_tags(self._key_tags).value = user_input
        self._constants.env_by_tags(self._enabled_tags).value = True
        return True

class ADSBHub(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="ADSBHub",
            tags=["adsb_hub"],
            system=system,
        )

    def _activate(self, user_input: str):
        return self._simple_activate(user_input)


class FlightRadar24(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="FlightRadar24",
            tags=["flightradar"],
            system=system,
        )

    def _request_fr24_sharing_key(self, email: str):
        if not self._download_docker_container(self.container):
            print_err("failed to download the FR24 docker image")
            return None

        cmdline = (
            f'--rm -i -e FEEDER_LAT="{self.lat}" -e FEEDER_LONG="{self.lng}" -e FEEDER_ALT_FT="{self.alt_ft}" '
            f'-e FR24_EMAIL="{email}" --entrypoint /scripts/signup.sh {self.container}'
        )
        output = self._docker_run_with_timeout(cmdline, 45.0)
        sharing_key_match = re.search(
            "Your sharing key \\(([a-zA-Z0-9]*)\\) has been", output
        )
        if not sharing_key_match:
            print_err(f"couldn't find a sharing key in the container output: {output}")
            return None

        return sharing_key_match.group(1)

    def _activate(self, user_input: str):
        if not user_input:
            return False
        if re.match(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", user_input
        ):
            # that's an email address, so we are looking to get a sharing key
            sharing_key = self._request_fr24_sharing_key(user_input)
            print_err(f"got back sharing_key |{sharing_key}|")
        elif re.match("[0-9a-zA-Z]+", user_input):
            # that might be a valid key
            sharing_key = user_input
        else:
            # hmm, that's weird. we need some error return, I guess
            print_err(
                f"we got a text that's neither email address nor sharing key: {user_input}"
            )
            return False
        # we have a sharing key, let's just enable the container
        self._constants.env_by_tags(self._key_tags).value = sharing_key
        self._constants.env_by_tags(self._enabled_tags).value = True

        return True

class PlaneWatch(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="PlaneWatch",
            tags=["planewatch"],
            system=system,
        )

    def _activate(self, user_input: str):
        return self._simple_activate(user_input)

class FlightAware(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="FlightAware",
            tags=["flightaware"],
            system=system,
        )

    def _request_fa_feeder_id(self):
        if not self._download_docker_container(self.container):
            print_err("failed to download the piaware docker image")
            return None

        cmdline = f"--rm {self.container}"
        output = self._docker_run_with_timeout(cmdline, 45.0)
        feeder_id_match = re.search(" feeder ID is ([-a-zA-Z0-9]*)", output)
        if feeder_id_match:
            return feeder_id_match.group(1)
        print_err(f"couldn't find a feeder ID in the container output: {output}")
        return None

    def _activate(self, user_input: str):
        if re.match("[0-9a-zA-Z]+", user_input):
            # that might be a valid key
            feeder_id = user_input
        else:
            feeder_id = self._request_fa_feeder_id()
            print_err(f"got back feeder_id |{feeder_id}|")
        if not feeder_id:
            return False

        self._constants.env_by_tags(self._key_tags).value = feeder_id
        self._constants.env_by_tags(self._enabled_tags).value = True


class RadarBox(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="RadarBox",
            tags=["radarbox"],
            system=system,
        )

    def _request_rb_sharing_key(self):
        docker_image = self._constants.env_by_tags(["radarbox", "container"]).value

        if not self._download_docker_container(docker_image):
            print_err("failed to download the RadarBox docker image")
            return None

        cmdline = (
            f"--rm -i --network adsb_default -e BEASTHOST=ultrafeeder -e LAT={self.lat} "
            f"-e LONG={self.lng} -e ALT={self.alt} {docker_image}"
        )
        output = self._docker_run_with_timeout(cmdline, 45.0)
        sharing_key_match = re.search("Your new key is ([a-zA-Z0-9]*)", output)
        if not sharing_key_match:
            print_err(f"couldn't find a sharing key in the container output: {output}")
            return None

        return sharing_key_match.group(1)

    def _activate(self, user_input: str):
        if re.match("[0-9a-zA-Z]+", user_input):
            # that might be a valid key
            sharing_key = user_input
        else:
            # try to get a key
            sharing_key = self._request_rb_sharing_key()
        if not sharing_key:
            return False

        self._constants.env_by_tags(self._key_tags).value = sharing_key
        self._constants.env_by_tags(self._enabled_tags).value = True
        return True


class OpenSky(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="OpenSky Network",
            tags=["opensky"],
            system=system,
        )

    def _activate(self, user_input: str):
        user, serial = user_input.split("::")
        if not user or not serial:
            print_err(f"can't parse {user_input} as user/serial for OpenSky")
            return False
        self._constants.env_by_tags(self.tags + ["user"]).value = user
        self._constants.env_by_tags(self.tags + ["pass"]).value = serial
        self._constants.env_by_tags(self.tags + ["is_enabled"]).value = True
        return True



class RadarVirtuel(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="RadarVirtuel",
            tags=["radarvirtuel"],
            system=system,
        )

    def _activate(self, user_input: str):
        return self._simple_activate(user_input)


class PlaneFinder(Aggregator):
    def __init__(self, system: System):
        super().__init__(
            name="PlaneFinder",
            tags=["planefinder"],
            system=system,
        )

    def _activate(self, user_input: str):
        return self._simple_activate(user_input)
