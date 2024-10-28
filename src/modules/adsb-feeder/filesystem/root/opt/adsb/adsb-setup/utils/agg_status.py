import json
import re
import subprocess
import requests
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from .util import generic_get_json, print_err, make_int, run_shell_captured
from .data import Data

T = Enum("T", ["Disconnected", "Unknown", "Good", "Bad", "Warning", "Unsupported", "Starting", "ContainerDown"])
status_symbol = {
    T.Disconnected: "\u2612",
    T.Unknown: ".",
    T.Good: "+",
    T.Bad: "\u2639",
    T.Warning: "\u26A0",
    T.Unsupported: " ",
    T.Starting: "\u27F3",
    T.ContainerDown: "\u2608",
}
ultrafeeder_aggs = [
    "adsblol",
    "flyitaly",
    "avdelphi",
    "planespotters",
    "tat",
    "radarplane",
    "adsbfi",
    "adsbx",
    "hpradar",
    "alive",
]

containerCheckLock = threading.Lock()
lastContainerCheck = 0
dockerPsCache = dict()


def refreshDockerPs():
    global dockerPsCache
    dockerPsCache = dict()
    cmdline = "docker ps --filter status=running --format '{{.Names}};{{.Status}}'"
    success, output = run_shell_captured(cmdline)
    if not success:
        print_err(f"Error: cmdline: {cmdline} output: {output}")
        return

    for line in output.split("\n"):
        if ";" in line:
            name, status = line.split(";")
            dockerPsCache[name] = status


def getContainerStatus(name):
    global lastContainerCheck
    global dockerPsCache
    with containerCheckLock:
        now = time.time()
        if now - lastContainerCheck > 10:
            refreshDockerPs()
            lastContainerCheck = now

        status = dockerPsCache.get(name)
        # print_err(f"{name}: {status}")
        if not status:
            # assume down
            return "down"

        if not status.startswith("Up"):
            return "down"

        try:
            up, number, unit = status.split(" ")
            if unit == "seconds" and int(number) < 30:
                # container up for less than 30 seconds, show 'starting'
                return "starting"
        except:
            pass

        return "up"


class AggStatus:
    def __init__(self, agg: str, idx, data: Data, url: str):
        self.lock = threading.Lock()
        self._agg = agg
        self._idx = make_int(idx)
        self._last_check = datetime.fromtimestamp(0.0)
        self._beast = T.Unknown
        self._mlat = T.Unknown
        self._d = data
        self._url = url
        self.check()

    @property
    def beast(self) -> str:
        if self.check():
            return status_symbol.get(self._beast, ".")
        return "."

    @property
    def mlat(self) -> str:
        if self.check():
            return status_symbol.get(self._mlat, ".")
        return "."

    def get_json(self, json_url):
        return generic_get_json(json_url, None)

    def get_plain(self, plain_url):
        requests.packages.urllib3.util.connection.HAS_IPV6 = False
        status = -1
        try:
            response = requests.get(
                plain_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/117.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                },
            )
        except (
            requests.HTTPError,
            requests.ConnectionError,
            requests.Timeout,
            requests.RequestException,
        ) as err:
            print_err(f"checking {plain_url} failed: {err}")
            status = err.errno
        except:
            # for some reason this didn't work
            print_err("checking {plain_url} failed: reason unknown")
        else:
            return response.text, response.status_code
        return None, status

    def uf_path(self):
        uf_dir = "/run/adsb-feeder-"
        uf_dir += f"uf_{self._idx}" if self._idx != 0 else "ultrafeeder"
        return uf_dir

    def get_mlat_status(self):
        mconf = None
        netconfig = self._d.netconfigs.get(self._agg)
        if not netconfig:
            print_err(f"ERROR: get_mlat_status called on {self._agg} not found in netconfigs: {self._d.netconfigs}")
            return
        mconf = netconfig.mlat_config
        # example mlat_config: "mlat,dati.flyitalyadsb.com,30100,39002",
        if not mconf:
            self._mlat = T.Unsupported
            return
        filename = f"{mconf.split(',')[1]}:{mconf.split(',')[2]}.json"
        try:
            mlat_json = json.load(open(f"{self.uf_path()}/mlat-client/{filename}", "r"))
            percent_good = mlat_json.get("good_sync_percentage_last_hour", 0)
            percent_bad = mlat_json.get("bad_sync_percentage_last_hour", 0)
            peer_count = mlat_json.get("peer_count", 0)
            now = mlat_json.get("now")
        except:
            #print_err(f"checking {self.uf_path()}/mlat-client/{filename} failed")
            self._mlat = T.Disconnected
            return
        if now - int(datetime.now().timestamp()) > 60:
            # that's more than a minute old... probably not connected
            self._mlat = T.Disconnected
        elif percent_good > 10 and percent_bad <= 5:
            self._mlat = T.Good
        elif percent_bad > 15:
            self._mlat = T.Bad
        else:
            self._mlat = T.Warning

        return

    def get_beast_status(self):
        bconf = None
        netconfig = self._d.netconfigs.get(self._agg)
        if not netconfig:
            print_err(f"ERROR: get_mlat_status called on {self._agg} not found in netconfigs: {self._d.netconfigs}")
            return
        bconf = netconfig.adsb_config
        # example adsb_config: "adsb,dati.flyitalyadsb.com,4905,beast_reduce_plus_out",
        if not bconf:
            print_err(f"ERROR: get_beast_status no netconfig for {self._agg}")
            return
        pattern = (
            f"readsb_net_connector_status{{host=\"{bconf.split(',')[1]}\",port=\"{bconf.split(',')[2]}\"}} (\\d+)"
        )
        filename = f"{self.uf_path()}/readsb/stats.prom"
        try:
            readsb_status = open(filename, "r").read()
        except:
            self._beast = T.Disconnected
            return
        match = re.search(pattern, readsb_status)
        if match:
            status = int(match.group(1))
            # this status is the time in seconds the connection has been established
            if status <= 0:
                self._beast = T.Disconnected
            elif status > 20:
                self._beast = T.Good
            else:
                self._beast = T.Warning

            #if self._beast != T.Good:
            #    print_err(f"beast check {self._agg :{' '}<{20}}: {self._beast} status: {status}")
        else:
            print_err(f"ERROR: no match checking beast for {pattern}")

        return

    def check(self):
        with self.lock:
            if datetime.now() - self._last_check < timedelta(seconds=10.0):
                return True

            self.check_impl()

            # if check_impl has updated last_check the status is available
            if datetime.now() - self._last_check < timedelta(seconds=10.0):
                return True

            return False

    def check_impl(self):
        if self._agg in ultrafeeder_aggs:
            container_name = "ultrafeeder" if self._idx == 0 else f"uf_{self._idx}"
        else:
            container_for_agg = {
                "radarbox": "rbfeeder",
                "planefinder": "pfclient",
                "flightaware": "piaware",
                "radarvirtuel": "radarvirtuel",
                "1090uk": "radar1090uk",
                "flightradar": "fr24feed",
                "opensky": "opensky",
                "adsbhub": "adsbhub",
                "planewatch": "planewatch",
            }
            container_name = container_for_agg.get(self._agg)
            if self._idx != 0:
                container_name += f"_{self._idx}"

        if container_name:
            container_status = getContainerStatus(container_name)
            if container_status == "down":
                self._beast = T.ContainerDown
                self._mlat = T.Unsupported
                self._last_check = datetime.now()
                return
            if container_status == "starting":
                self._beast = T.Starting
                self._mlat = T.Unsupported
                self._last_check = datetime.now()
                return

        # for the Ultrafeeder based aggregators, let's not bother with talking to their API
        # that's of course bogus as hell - simply remove all the code for thsoe aggregators
        # below - but for now I'm not sure I want to do this because I'm not sure it's the
        # right thing to do
        if self._agg in ultrafeeder_aggs:
            self.get_mlat_status()
            self.get_beast_status()
            self._last_check = datetime.now()
            return

        if self._agg == "adsblol":
            uuid = self._d.env_by_tags("adsblol_uuid").list_get(self._idx)
            name = self._d.env_by_tags("site_name").list_get(self._idx)
            json_url = "https://api.adsb.lol/0/me"
            response_dict, status = self.get_json(json_url)
            if response_dict and status == 200:
                lolclients = response_dict.get("clients")
                if lolclients:
                    lolbeast = lolclients.get("beast")
                    lolmlat = lolclients.get("mlat")
                    self._beast = T.Disconnected
                    if isinstance(lolbeast, list):
                        for entry in lolbeast:
                            if entry.get("uuid", "xxxxxxxx-xxxx-")[:14] == uuid[:14]:
                                self._beast = T.Good
                                self._d.env_by_tags("adsblol_link").list_set(self._idx, entry.get("adsblol_my_url"))
                                break
                    self._mlat = (
                        T.Good
                        if isinstance(lolmlat, list)
                        and any(b.get("uuid", "xxxxxxxx-xxxx-")[:14] == uuid[:14] for b in lolmlat)
                        else T.Disconnected
                    )
                    self._last_check = datetime.now()
                else:
                    print_err(f"adsblol returned status {status}")
        elif self._agg == "flyitaly":
            # get the data from json
            json_url = "https://my.flyitalyadsb.com/am_i_feeding"
            response_dict, status = self.get_json(json_url)
            if response_dict and status == 200:
                feeding = response_dict["feeding"]
                if feeding:
                    self._beast = T.Good if feeding.get("beast") else T.Disconnected
                    self._mlat = T.Good if feeding.get("mlat") else T.Disconnected
                    self._last_check = datetime.now()
            else:
                print_err(f"flyitaly returned {status}")
        elif self._agg == "adsbfi":
            # get the data from json
            # get beast from https://api.adsb.fi/v1/feeder?id=uuid
            # and get mlat from myip with name match
            uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
            name = self._d.env_by_tags("site_name").list_get(self._idx)
            json_uuid_url = f"https://api.adsb.fi/v1/feeder?id={uuid}"

            """
            # the following should no longer be true, probably was caused my a
            # bug in mlat-client when passing uuid on the command line

            # we are having an easier time finding mlat data via the myip api
            # as apparently mlathub doesn't always send the right uuid
            json_ip_url = "https://api.adsb.fi/v1/myip"
            adsbfi_dict, status = self.get_json(json_ip_url)
            if adsbfi_dict and status == 200:
                mlat_array = adsbfi_dict.get("mlat", [])
                self._mlat = T.Good if any(m.get("user", "") == name for m in mlat_array) else T.Disconnected
                self._last_check = datetime.now()
            else:
                print_err(f"adsbfi v1/myip returned {status}")
            """

            adsbfi_dict, status = self.get_json(json_uuid_url)
            if adsbfi_dict and status == 200:
                beast_array = adsbfi_dict.get("beast", [])
                self._beast = (
                    T.Good if len(beast_array) > 0 and beast_array[0].get("receiverId") == uuid else T.Disconnected
                )
                mlat_array = adsbfi_dict.get("mlat", [])
                self._mlat = (
                    T.Good if len(mlat_array) > 0 and mlat_array[0].get("receiverId") == uuid else T.Disconnected
                )
                self._last_check = datetime.now()
            else:
                print_err(f"adsbfi v1/feeder returned {status}")
        elif self._agg == "radarplane":
            json_url = "https://radarplane.com/api/v1/feed/check"
            radarplane_dict, status = self.get_json(json_url)
            if radarplane_dict and status == 200:
                rdata = radarplane_dict.get("data")
                if rdata:
                    self._beast = T.Good if rdata.get("beast") else T.Disconnected
                    self._mlat = T.Good if rdata.get("mlat") else T.Disconnected
                    self._last_check = datetime.now()
            else:
                print_err(f"radarplane returned {status}")
        elif self._agg == "flightaware":
            suffix = "" if self._idx == 0 else f"_{self._idx}"
            json_url = f"{self._url}/fa-status.json{suffix}/"
            fa_dict, status = self.get_json(json_url)
            if fa_dict and status == 200:
                # print_err(f"fa status.json returned {fa_dict}")
                self._beast = (
                    T.Good
                    if fa_dict.get("adept") and fa_dict.get("adept").get("status") == "green"
                    else T.Disconnected
                )

                self._mlat = T.Disconnected
                if fa_dict.get("mlat"):
                    if fa_dict.get("mlat").get("status") == "green":
                        self._mlat = T.Good
                    elif fa_dict.get("mlat").get("status") == "amber":
                        message = fa_dict.get("mlat").get("message").lower()
                        if "unstable" in message:
                            self._mlat = T.Bad
                        elif "initializing" in message:
                            self._mlat = T.Unknown
                        elif "no clock sync" in message:
                            self._mlat = T.Warning
                        else:
                            self._mlat = T.Unknown
                    else:
                        self._mlat = T.Disconnected

                self._last_check = datetime.now()
            else:
                print_err(f"flightaware at {json_url} returned {status}")
        elif self._agg == "flightradar":
            self._mlat = T.Unsupported
            suffix = "" if self._idx == 0 else f"_{self._idx}"
            json_url = f"{self._url}/fr24-monitor.json{suffix}"
            fr_dict, status = self.get_json(json_url)
            if fr_dict and status == 200:
                # print_err(f"fr monitor.json returned {fr_dict}")
                self._beast = T.Good if fr_dict.get("feed_status") == "connected" else T.Disconnected
                self._last_check = datetime.now()
            else:
                print_err(f"flightradar at {json_url} returned {status}")
        elif self._agg == "radarplane":
            uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
            json_url = f"https://radarplane.com/api/v1/feed/check/{uuid}"
            rp_dict, status = self.get_json(json_url)
            if rp_dict and rp_dict.get("data") and status == 200:
                self._beast = T.Good if rp_dict["data"].get("beast") else T.Disconnected
                self._mlat = T.Good if rp_dict["data"].get("mlat") else T.Disconnected
                self._last_check = datetime.now()
            else:
                print_err(f"radarplane returned {status}")
        elif self._agg == "radarbox":

            rbkey = self._d.env_by_tags(["radarbox", "key"]).list_get(self._idx)
            # reset station number if the key has changed
            if rbkey != self._d.env_by_tags(["radarbox", "snkey"]).list_get(self._idx):
                station_serial = self._d.env_by_tags(["radarbox", "sn"]).list_set(self._idx, "")

            station_serial = self._d.env_by_tags(["radarbox", "sn"]).list_get(self._idx)
            if not station_serial:
                # dang, I hate this part
                suffix = "" if self._idx == 0 else f"_{self._idx}"
                try:
                    result = subprocess.run(
                        f"docker logs rbfeeder{suffix} | grep 'station serial number' | tail -1",
                        shell=True,
                        capture_output=True,
                        text=True,
                    )
                except:
                    print_err("got exception trying to look at the rbfeeder logs")
                    return
                serial_text = result.stdout.strip()
                match = re.search(r"This is your station serial number: ([A-Z0-9]+)", serial_text)
                if match:
                    station_serial = match.group(1)
                    self._d.env_by_tags(["radarbox", "sn"]).list_set(self._idx, station_serial)
                    self._d.env_by_tags(["radarbox", "snkey"]).list_set(self._idx, rbkey)
            if station_serial:
                html_url = f"https://www.radarbox.com/stations/{station_serial}"
                rb_page, status = self.get_plain(html_url)
                match = re.search(r"window.init\((.*)\)", rb_page)
                if match:
                    rb_json = match.group(1)
                    rb_dict = json.loads(rb_json)
                    station = rb_dict.get("station")
                    if station:
                        online = station.get("online")
                        mlat_online = station.get("mlat_online")
                        self._beast = T.Good if online else T.Disconnected
                        self._mlat = T.Good if mlat_online else T.Disconnected
                        self._last_check = datetime.now()
        elif self._agg == "1090uk":
            key = self._d.env_by_tags(["1090uk", "key"]).list_get(self._idx)
            json_url = f"https://www.1090mhz.uk/mystatus.php?key={key}"
            tn_dict, status = self.get_json(json_url)
            if tn_dict and status == 200:
                online = tn_dict.get("online", False)
                self._beast = T.Good if online else T.Disconnected
            else:
                self._beast = T.Unknown

            self._last_check = datetime.now()
            self._mlat = T.Unsupported

        elif self._agg == "planefinder":
            self._beast = T.Unknown
            self._mlat = T.Unsupported
            self._last_check = datetime.now()
        elif self._agg == "adsbhub":
            self._beast = T.Unknown
            self._mlat = T.Unsupported
            self._last_check = datetime.now()
        elif self._agg == "opensky":
            self._beast = T.Unknown
            self._mlat = T.Unsupported
            self._last_check = datetime.now()
        elif self._agg == "radarvirtuel":
            self._beast = T.Unknown
            self._mlat = T.Unknown
            self._last_check = datetime.now()
        elif self._agg == "alive":
            json_url = "https://api.airplanes.live/feed-status"
            a_dict, status = self.get_json(json_url)
            if a_dict and status == 200:
                uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
                beast_clients = a_dict.get("beast_clients")
                # print_err(f"alife returned {beast_clients}", level=8)
                if beast_clients:
                    self._beast = T.Good if any(bc.get("uuid") == uuid for bc in beast_clients) else T.Disconnected
                mlat_clients = a_dict.get("mlat_clients")
                # print_err(f"alife returned {mlat_clients}")
                if mlat_clients:
                    self._mlat = (
                        T.Good
                        if any(
                            (isinstance(mc.get("uuid"), list) and mc.get("uuid")[0] == uuid)
                            or (isinstance(mc.get("uuid"), str) and mc.get("uuid") == uuid)
                            for mc in mlat_clients
                        )
                        else T.Disconnected
                    )
                map_link = a_dict.get("map_link")
                # seems to currently only have one map link per IP, we save it
                # per microsite nonetheless in case this changes in the future
                if map_link:
                    self._d.env_by_tags("alivemaplink").list_set(self._idx, map_link)
                self._last_check = datetime.now()
            else:
                print_err(f"airplanes.james returned {status}")
        elif self._agg == "adsbx":
            feeder_id = self._d.env_by_tags("adsbxfeederid").list_get(self._idx)
            if not feeder_id or len(feeder_id) != 12:
                # get the adsbexchange feeder id for the anywhere map / status things
                print_err(f"don't have the adsbX Feeder ID for {self._idx}, yet")
                container_name = "ultrafeeder" if self._idx == 0 else f"uf_{self._idx}"
                try:
                    result = subprocess.run(
                        f"docker logs {container_name} | grep 'www.adsbexchange.com/api/feeders' | tail -1",
                        shell=True,
                        capture_output=True,
                        text=True,
                    )
                    output = result.stdout
                except:
                    print_err("got exception trying to look at the adsbx logs")
                    return
                match = re.search(
                    r"www.adsbexchange.com/api/feeders/\?feed=([^&\s]*)",
                    output,
                )
                if match:
                    adsbx_id = match.group(1)
                    self._d.env_by_tags("adsbxfeederid").list_set(self._idx, adsbx_id)
                else:
                    print_err(f"ran: docker logs {container_name} | grep 'www.adsbexchange.com/api/feeders' | tail -1")
                    print_err(f"failed to find adsbx ID in response {output}")

            self._last_check = datetime.now()
            # the checks below are no longer needed due to the generalized ultrafeeder status checks
            """
            # let's check the ultrafeeder net connector status to see if there is a TCP beast connection to adsbexchange
            try:
                suffix = "ultrafeeder" if self._idx == 0 else f"uf_{self._idx}"
                result = subprocess.run(
                    f"grep -F -e adsbexchange.com /run/adsb-feeder-{suffix}/readsb/stats.prom | cut -d' ' -f2",
                    shell=True,
                    capture_output=True,
                    text=True,
                )
                try:
                    tcp_uptime = int(result.stdout)
                except:
                    print_err(f"WARNING: adsbx tcp uptime check returned: {result.stdout}")
                self._beast = T.Good if tcp_uptime > 5 else T.Disconnected
            except:
                self._beast = T.Disconnected
                pass
            # now check mlat - which we can't really get easily from their status page
            # but can get from our docker logs again
            container_name = "ultrafeeder" if self._idx == 0 else f"uf_{self._idx}"
            try:
                result = subprocess.run(
                    f"docker logs --since=20m {container_name} | grep '\[mlat-client]\[feed.adsbexchange.com] peer_count' | tail -n1",
                    shell=True,
                    capture_output=True,
                    text=True,
                )
            except:
                print_err(f"got exception trying to look at the adsbx docker logs from {container_name}")
                return
            match = re.search(
                r".mlat-client..feed.adsbexchange.com. peer_count:\s*([0-9.]*)\s*outlier_percent:\s*([0-9.]*)\s*bad_sync_timeout:\s*([0-9.]*)",
                result.stdout,
            )
            if match:
                peer_count = make_int(match.group(1))
                bad_sync_timeout = make_int(match.group(3))
                # print_err(f"peer_count: {peer_count} bad_sync: {bad_sync_timeout}")
                self._mlat = T.Good if peer_count > 0 and bad_sync_timeout == 0 else T.Disconnected
            else:
                self._mlat = T.Unknown
            """

        elif self._agg == "tat":
            # get the data from the status text site
            text_url = "https://theairtraffic.com/iapi/feeder_status"
            tat_text, status = self.get_plain(text_url)
            if text_url and status == 200:
                if re.search(r" No ADS-B feed", tat_text):
                    self._beast = T.Disconnected
                elif re.search(r"  ADS-B feed", tat_text):
                    self._beast = T.Good
                else:
                    print_err(f"can't parse beast part of tat response")
                    return
                if re.search(r" No MLAT feed", tat_text):
                    self._mlat = T.Disconnected
                elif re.search(r"  MLAT feed", tat_text):
                    self._mlat = T.Good
                else:
                    print_err(f"can't parse mlat part of tat response")
                    self._mlat = T.Unknown
                    # but since we got someting we could parse for beast above, let's keep going

                self._last_check = datetime.now()
            else:
                print_err(f"tat returned {status}")
        elif self._agg == "planespotters":
            uf_uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
            html_url = f"https://www.planespotters.net/feed/status/{uf_uuid}"
            ps_text, status = self.get_plain(html_url)
            if ps_text and status == 200:
                self._beast = T.Disconnected if re.search("Feeder client not connected", ps_text) else T.Good
                self._last_check = datetime.now()
            else:
                print_err(f"planespotters returned {status}")
        elif self._agg == "planewatch":
            # they sometimes call it key, sometimes uuid
            pw_uuid = self._d.env_by_tags(["planewatch", "key"]).list_get(self._idx)
            if not pw_uuid:
                return
            json_url = f"https://atc.plane.watch/api/v1/feeders/{pw_uuid}/status.json"
            pw_dict, status = self.get_json(json_url)
            if pw_dict and status == 200:
                status = pw_dict.get("status")
                if not status:
                    print_err(f"can't parse planewatch status {pw_dict}")
                    return
                adsb = status.get("adsb")
                mlat = status.get("mlat")
                if not adsb or not mlat:
                    print_err(f"can't parse planewatch status {pw_dict}")
                    return
                self._beast = T.Good if adsb.get("connected") else T.Disconnected
                self._mlat = T.Good if mlat.get("connected") else T.Disconnected
                self._last_check = datetime.now()
            else:
                print_err(f"planewatch returned {status}")

        # if mlat isn't enabled ignore status check results
        if not self._d.list_is_enabled("mlat_enable", self._idx):
            self._mlat = T.Unsupported

    def __repr__(self):
        return f"Aggregator({self._agg} last_check: {str(self._last_check)}, beast: {self._beast} mlat: {self._mlat})"


class ImStatus:
    def __init__(self, data: Data):
        self._d = data

    def check(self):
        json_url = f"https://adsb.im/api/status"
        return generic_get_json(json_url, self._d.env_by_tags("pack").value)
