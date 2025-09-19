import json
import re
import subprocess
import requests
import threading
import traceback
import time
import pathlib
import os
from datetime import datetime, timedelta
from enum import Enum
from .util import generic_get_json, print_err, make_int, run_shell_captured, get_plain_url
from .data import Data

T = Enum("T", ["Disconnected", "Unknown", "Good", "Bad", "Warning", "Disabled", "Starting", "ContainerDown"])
# deprecated status symbol, might be useful again for something?
status_symbol = {
    T.Disconnected: "\u2612",
    T.Unknown: ".",
    T.Good: "+",
    T.Bad: "\u2639",
    T.Warning: "\u26a0",
    T.Disabled: " ",
    T.Starting: "\u27f3",
    T.ContainerDown: "\u2608",
}
status_short = {
    T.Disconnected: "disconnected",
    T.Unknown: "unknown",
    T.Good: "good",
    T.Bad: "bad",
    T.Warning: "warning",
    T.Disabled: "disabled",
    T.Starting: "starting",
    T.ContainerDown: "container_down",
}
ultrafeeder_aggs = [
    "adsblol",
    "flyitaly",
    "avdelphi",
    "planespotters",
    "tat",
    "adsbfi",
    "adsbx",
    "hpradar",
    "alive",
]


class AggStatus:
    def __init__(self, agg: str, idx, data: Data, url: str, system):
        self.lock = threading.Lock()
        self._agg = agg
        self._idx = make_int(idx)
        self._last_check = datetime.fromtimestamp(0.0)
        self._beast = T.Unknown
        self._mlat = T.Unknown
        self._d = data
        self._url = url
        self._system = system

    @property
    def beast(self) -> str:
        if self.check():
            return status_short.get(self._beast, ".")
        return "."

    @property
    def mlat(self) -> str:
        if self.check():
            return status_short.get(self._mlat, ".")
        return "."

    def get_json(self, json_url):
        return generic_get_json(json_url, None)

    def uf_path(self):
        uf_dir = "/run/adsb-feeder-"
        uf_dir += f"uf_{self._idx}" if self._idx != 0 else "ultrafeeder"
        return uf_dir

    def get_mlat_status(self, path=None):
        # if mlat isn't enabled ignore status check results
        if not self._d.list_is_enabled("mlat_enable", self._idx):
            self._mlat = T.Disabled
            return
        if not path:
            mconf = None
            netconfig = self._d.netconfigs.get(self._agg)
            if not netconfig:
                print_err(
                    f"ERROR: get_mlat_status called on {self._agg} not found in netconfigs: {self._d.netconfigs}"
                )
                return
            mconf = netconfig.mlat_config
            # example mlat_config: "mlat,dati.flyitalyadsb.com,30100,39002",
            if not mconf:
                self._mlat = T.Disabled
                return
            filename = f"{mconf.split(',')[1]}:{mconf.split(',')[2]}.json"
            path = f"{self.uf_path()}/mlat-client/{filename}"
        try:
            mlat_json = json.load(open(path, "r"))
            percent_good = mlat_json.get("good_sync_percentage_last_hour", 0)
            percent_bad = mlat_json.get("bad_sync_percentage_last_hour", 0)
            peer_count = mlat_json.get("peer_count", 0)
            now = mlat_json.get("now")
        except:
            self._mlat = T.Disconnected
            return
        if time.time() - now > 60:
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

            # if self._beast != T.Good:
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
        # print_err(f"agg_status check_impl for {self._agg}-{self._idx}")
        if self._agg in ultrafeeder_aggs:
            container_name = "ultrafeeder" if self._idx == 0 else f"uf_{self._idx}"
        else:
            container_for_agg = {
                "radarbox": "rbfeeder",
                "planefinder": "pfclient",
                "flightaware": "piaware",
                "radarvirtuel": "radarvirtuel",
                "1090uk": "1090uk",
                "flightradar": "fr24feed",
                "opensky": "opensky",
                "adsbhub": "adsbhub",
                "planewatch": "planewatch",
                "sdrmap": "sdrmap",
            }
            container_name = container_for_agg.get(self._agg)
            if self._idx != 0:
                container_name += f"_{self._idx}"

        container_status = None
        if container_name:
            container_status = self._system.getContainerStatus(container_name)

        # for the Ultrafeeder based aggregators, let's not bother with talking to their API
        # readsb / mlat-client provide information about the feed status for those
        if self._agg in ultrafeeder_aggs:
            self.get_mlat_status()
            self.get_beast_status()
            self._last_check = datetime.now()
            self.get_maplink()

        if container_status is None:
            pass # status unknown
        elif container_status == "down":
            self._beast = T.ContainerDown
            self._mlat = T.Disabled
            self._last_check = datetime.now()
            return
        elif container_status == "up":
            pass
        elif "up for" in container_status:
            _, _, uptime = container_status.split(" ")
            uptime = int(uptime)
            if self._agg not in ultrafeeder_aggs:
                if uptime < 60:
                    self._beast = T.Starting
                    self._mlat = T.Disabled
                    self._last_check = datetime.now()
                    return

            if self._agg in ultrafeeder_aggs:
                if uptime < 30:
                    # overwrite the status we got above
                    self._beast = T.Starting
                    self._mlat = T.Starting
                    self._last_check = datetime.now()
                    return
                if uptime < 60:
                    # use beast status that has been determined above
                    self._mlat = T.Starting
                    self._last_check = datetime.now()
                    return

        if self._agg == "flightaware":
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
            self._mlat = T.Disabled
            suffix = "" if self._idx == 0 else f"_{self._idx}"
            json_url = f"{self._url}/fr24-monitor.json{suffix}/"
            fr_dict, status = self.get_json(json_url)
            if fr_dict and status == 200:
                # print_err(f"fr monitor.json returned {fr_dict}")
                self._beast = T.Good if fr_dict.get("feed_status") == "connected" else T.Disconnected
                self._last_check = datetime.now()
            else:
                print_err(f"flightradar at {json_url} returned {status}")
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
                rb_page, status = get_plain_url(html_url)
                match = re.search(r"window.init\((.*)\)", rb_page) if rb_page else None
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
            self._beast = T.Unknown
            self._mlat = T.Disabled
            if False:
                key = self._d.env_by_tags(["1090uk", "key"]).list_get(self._idx)
                json_url = f"https://www.1090mhz.uk/mystatus.php?key={key}"
                tn_dict, status = self.get_json(json_url)
                if tn_dict and status == 200:
                    online = tn_dict.get("online", False)
                    self._beast = T.Good if online else T.Disconnected
                else:
                    self._beast = T.Unknown

            self._last_check = datetime.now()

        elif self._agg == "planefinder":
            self._beast = T.Unknown
            self._mlat = T.Disabled
            self._last_check = datetime.now()
        elif self._agg == "adsbhub":
            self._beast = T.Unknown
            self._mlat = T.Disabled
            self._last_check = datetime.now()
        elif self._agg == "opensky":
            self._beast = T.Unknown
            self._mlat = T.Disabled
            self._last_check = datetime.now()
        elif self._agg == "radarvirtuel":
            self._beast = T.Unknown
            self._mlat = T.Unknown
            self._last_check = datetime.now()

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
        elif self._agg == "sdrmap":
            self._last_check = datetime.now()
            if os.path.exists(f"/run/sdrmap_{self._idx}/feed_ok"):
                self._beast = T.Good
            else:
                self._beast = T.Disconnected
            # self.get_mlat_status(path=f"/run/sdrmap_{self._idx}/mlat-client-stats.json")
            self._mlat = T.Unknown

        # if mlat isn't enabled ignore status check results
        if not self._d.list_is_enabled("mlat_enable", self._idx):
            self._mlat = T.Disabled

    def get_maplink(self):
        if self._agg == "alive":
            self.check_alive_maplink()

        if self._agg == "adsblol" and not self._d.env_by_tags("adsblol_link").list_get(self._idx):
            uuid = self._d.env_by_tags("adsblol_uuid").list_get(self._idx)
            json_url = "https://api.adsb.lol/0/me"
            response_dict, status = self.get_json(json_url)
            if response_dict and status == 200:
                try:
                    for entry in response_dict.get("clients").get("beast"):
                        if entry.get("uuid", "xxxxxxxx-xxxx-")[:14] == uuid[:14]:
                            self._d.env_by_tags("adsblol_link").list_set(self._idx, entry.get("adsblol_my_url"))
                except:
                    print_err(traceback.format_exc())

        if self._agg == "adsbx":
            # get the adsbexchange feeder id for the anywhere map / status things
            feeder_id = self.adsbx_feeder_id()

    def check_alive_maplink(self):
        # currently airplanes live uses the first 16 characters of the uuid as the feed id
        # this works better than getting it for the API because the API only returns 1 feed id
        uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
        feed_id = uuid.replace("-", "")[:16]
        map_link = f"https://globe.airplanes.live/?feed={feed_id}"
        self._d.env_by_tags("alivemaplink").list_set(self._idx, map_link)

        return

        # alternatively get it from their api (currently dead code)
        # maybe keep that if they change the above pattern in the future:
        if self._d.env_by_tags("alivemaplink").list_get(self._idx):
            return
        json_url = "https://api.airplanes.live/feed-status"
        a_dict, status = self.get_json(json_url)
        if a_dict and status == 200:
            map_link = a_dict.get("map_link")
            # seems to currently only have one map link per IP, we save it
            # per microsite nonetheless in case this changes in the future
            if map_link:
                self._d.env_by_tags("alivemaplink").list_set(self._idx, map_link)

    def adsbx_feeder_id(self):
        feeder_id = self._d.env_by_tags("adsbxfeederid").list_get(self._idx)
        uuid_saved = self._d.env_by_tags("adsbxfeederid_uuid").list_get(self._idx)
        uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
        if uuid_saved != uuid or not feeder_id or len(feeder_id) != 12:
            # get the adsbexchange feeder id for the anywhere map / status things
            print_err(f"don't have the adsbX Feeder ID for {self._idx}, yet")
            output, status = get_plain_url(f"https://www.adsbexchange.com/api/feeders/tar1090/?feed={uuid}")
            match = re.search(
                r"www.adsbexchange.com/api/feeders/\?feed=([^\"'&\s]*)",
                output,
            )
            adsbx_id = None
            if match:
                adsbx_id = match.group(1)
            if adsbx_id and len(adsbx_id) == 12:
                print_err(f"adsbx feeder id for {self._idx}: {adsbx_id}")
                self._d.env_by_tags("adsbxfeederid").list_set(self._idx, adsbx_id)
                self._d.env_by_tags("adsbxfeederid_uuid").list_set(self._idx, uuid)
            else:
                print_err(f"failed to find adsbx ID in response {output}")

    def __repr__(self):
        return f"Aggregator({self._agg} last_check: {str(self._last_check)}, beast: {self._beast} mlat: {self._mlat})"


class ImStatus:
    def __init__(self, data: Data):
        self._d = data
        self._lock = threading.Lock()
        self._next_check = 0
        self._cached = None

    def check(self, check=False):
        with self._lock:
            if not self._cached or time.time() > self._next_check or check:
                json_url = f"https://adsb.im/api/status"
                self._cached, status = generic_get_json(json_url, self._d.env_by_tags("pack").value)
                if status == 200:
                    # good result, no need to update this sooner than in a minute
                    self._next_check = time.time() + 60
                    if self._d.previous_version and not check:
                        self._d.previous_version = ""
                        pathlib.Path("/opt/adsb/adsb.im.previous-version").unlink(missing_ok=True)

                elif status == 201:
                    # successful check-in
                    return {"latest_tag": "success", "latest_commit": "", "advice": ""}
                else:
                    # check again no earlier than 10 seconds from now
                    self._next_check = time.time() + 10
                    print_err(f"adsb.im returned {status}")
                    self._cached = {
                        "latest_tag": "unknown",
                        "latest_commit": "",
                        "advice": "there was an error obtaining the latest version information",
                    }

            return self._cached

class LastSeen:
    def __init__(self):
        self.seen = None

    def update(self):
        self.seen = time.time()

    def tooLong(self, hours):
        if not self.seen:
            # last status is not kept across restarts for now, just assume we received a plane
            # just now, this isn't pretty but if we don't have restarts it's fine
            self.update()
        # 0 or negative means this check is disabled, always return false
        if hours <= 0:
            return False
        if time.time() - self.seen > hours * 3600:
            return True
        return False


class Healthcheck:
    def __init__(self, data):
        self._d = data
        self.good = True
        self.pingInterval = 60 * 60 # 60 minutes
        self.graceTime = 5 * 60 # 5 minutes from failure to failPing

        # first ping 1 minute after startup for the moment to avoid too frequent pings if stuck in
        # restart loop or something
        self.nextGoodPing = time.time() + 1 * 60
        self.nextFailPing = time.time() + 1 * 60

        self.failedSince = 0

        self.last1090 = LastSeen()
        self.last978 = LastSeen()
        self.lastAcars = LastSeen()
        self.lastAcars2 = LastSeen()
        self.lastVdl = LastSeen()

        self.lastReadsbUptime = -1
        self.lastReadsbSamples = -1

        self.pingURL = self._d.env_by_tags("healthcheck_url").value

    def set_good(self):
        if not self.good:
            print_err(f"healthcheck healthy after it was bad previously")
        self.good = True
        self.failedSince = 0
        self.reason = ""
        self._d.env_by_tags("healthcheck_fail_reason").value = ""

        if time.time() >= self.nextGoodPing:
            self.nextGoodPing = time.time() + self.pingInterval
            self.nextFailPing = time.time() # set next fail ping to be immediate
            if self._d.env_by_tags("healthcheck_url").value:
                page, status = get_plain_url(self._d.env_by_tags("healthcheck_url").value)
                if status != 200:
                    print_err(f"healthcheck url ping FAILURE: got http status {status}")
                    # failure, try again in a minute instead of waiting pingInterval
                    self.nextGoodPing = time.time() + 60
                print_err(f"healthcheck url ping success")

    def set_failed(self, reason):
        self.reason = reason
        if self.good:
            print_err(f"healthcheck failed with reason: {reason} (fail ping and UI notice only after 5 minutes of continued failure)")
            self.failedSince = time.time()
            self.good = False

        if time.time() - self.failedSince > 5 * 60:
            self._d.env_by_tags("healthcheck_fail_reason").value = reason
        if time.time() >= self.nextFailPing and time.time() - self.failedSince > 5 * 60:
            print_err(f"healthcheck failPing due to: {self.reason}")
            self.nextFailPing = time.time() + self.pingInterval
            self.nextGoodPing = time.time() # set next success ping to be immediate
            if self._d.env_by_tags("healthcheck_url").value:
                page, status = get_plain_url(self._d.env_by_tags("healthcheck_url").value + "/fail")
                if status != 200:
                    print_err(f"healthcheck url fail FAILURE: got http status {status}")
                    # failure, try again in a minute instead of waiting pingInterval
                    self.nextFailPing = time.time() + 60
                print_err(f"healthcheck url fail successfully signaled")


    # this is called every minute from app.py so we don't need to run another thread
    def check(self):
        fail = []
        adsb = not self._d.env_by_tags("aggregator_choice").value

        uf_path = "/run/adsb-feeder-"
        if self._d.env_by_tags("aggregator_choice").value == "nano":
            uf_path += "nanofeeder"
        else:
            uf_path += "ultrafeeder"

        try:
            with open(f"{uf_path}/readsb/stats.json") as f:
                obj = json.load(f)
                now = obj.get("now")
                if not now or now < time.time() - 60:
                    fail.append("readsb stats.json out of date")
                local = obj.get("total").get("local")
                if local:
                    samples = local.get("samples_processed")
                    if samples == self.lastReadsbSamples:
                        fail.append(f"1090 SDR hung (sample count: {samples})")
                    self.lastReadsbSamples = samples
        except:
            if adsb:
                print_err(traceback.format_exc())
                fail.append("readsb stats.json not found")

        if self._d.env_by_tags("1090serial").value != "":
            try:
                with open(f"{uf_path}/readsb/aircraft.json") as f:
                    obj = json.load(f)
                    ac = obj.get('aircraft')
                    seen = False
                    for a in ac:
                        t = a.get('type')
                        if t in ['adsb_icao', 'mode_s', 'mlat']:
                            seen = True
                    if seen:
                        self.last1090.update()
                    now = obj.get("now")
                    if not now or now < time.time() - 60:
                        fail.append("readsb aircraft.json out of date")
            except:
                print_err(traceback.format_exc())
                fail.append("readsb aircraft.json not found")

            hours = self._d.env_by_tags("healthcheck_noplane_hours_1090").value
            if self.last1090.tooLong(hours):
                fail.append(f"no planes 1090 for {hours}h")

        if self._d.env_by_tags("978serial").value != "":
            try:
                with open(f"/run/adsb-feeder-dump978/skyaware978/aircraft.json") as f:
                    obj = json.load(f)
                    ac = obj.get('aircraft')
                    seen = False
                    for a in ac:
                        if a.get('lat') != None:
                            seen = True
                    if seen:
                        self.last978.update()
                    now = obj.get("now")
                    if not now or now < time.time() - 60:
                        fail.append("dump978 aircraft.json out of date")
            except:
                print_err(traceback.format_exc())
                fail.append("dump978 aircraft.json not found")

            hours = self._d.env_by_tags("healthcheck_noplane_hours_978").value
            if self.last978.tooLong(hours):
                fail.append(f"no planes 978 for {hours}h")

        if self._d.is_enabled("airspy"):
            try:
                with open(f"/run/adsb-feeder-airspy/airspy_adsb/stats.json") as f:
                    obj = json.load(f)
                    now = obj.get("now")
                    if not now or now < time.time() - 90:
                        fail.append("airspy stats.json outdated")
            except:
                print_err(traceback.format_exc())
                fail.append("airspy stats.json not found")

        ''' needs some container changes first
        hours = self._d.env_by_tags("healthcheck_noacars_hours").value
        if self._d.is_enabled("run_acarsdec")
            if self.lastAcars.tooLong(hours):
                fail.append(f"no ACARS messages for {hours}h"
        if self._d.is_enabled("run_acarsdec2")
            if self.lastAcars2.tooLong(hours):
                fail.append(f"no ACARS2 messages for {hours}h"
        if self._d.is_enabled("run_dumpvdl2")
            if self.lastVdl.tooLong(hours):
                fail.append(f"no VDL messages for {hours}h"
        '''


        if self.pingURL != self._d.env_by_tags("healthcheck_url").value:
            self.pingURL = self._d.env_by_tags("healthcheck_url").value
            # reset the ping timers so the first ping happens quickly after a user sets the URL
            self.nextGoodPing = time.time()
            self.nextFailPing = time.time()

        fail = "; ".join(fail)
        if fail:
            self.set_failed(fail)
        else:
            self.set_good()
