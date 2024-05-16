import json
import re
import subprocess
import requests
from datetime import datetime, timedelta
from enum import Enum
from .util import generic_get_json, print_err, make_int
from .data import Data

T = Enum("T", ["Yes", "No", "Unknown"])


class AggStatus:
    def __init__(self, agg: str, idx, data: Data, url: str):
        self._agg = agg
        self._idx = make_int(idx)
        self._last_check = datetime.fromtimestamp(0.0)
        self._beast = T.Unknown
        self._mlat = T.Unknown
        self._d = data
        self._url = url
        self.check()

    def use_cached(self, now):
        return now - self._last_check < timedelta(seconds=10.0)

    @property
    def beast(self) -> str:
        now = datetime.now()
        if not self.use_cached(now):
            self.check()
        if self.use_cached(now):
            return "+" if self._beast == T.Yes else "-" if self._beast == T.No else "."
        return "."

    @property
    def mlat(self) -> str:
        now = datetime.now()
        if not self.use_cached(now):
            self.check()
        if self.use_cached(now):
            return "+" if self._mlat == T.Yes else "-" if self._mlat == T.No else "."
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

    def check(self):
        # figure out the feeder state at this aggregator (if possible)
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
                    self._beast = T.No
                    if isinstance(lolbeast, list):
                        for entry in lolbeast:
                            if entry.get("uuid", "xxxxxxxx-xxxx-")[:14] == uuid[:14]:
                                self._beast = T.Yes
                                self._d.env_by_tags("adsblol_link").list_set(
                                    self._idx, entry.get("adsblol_my_url")
                                )
                                break
                    self._mlat = (
                        T.Yes
                        if isinstance(lolmlat, list)
                        and any(
                            b.get("uuid", "xxxxxxxx-xxxx-")[:14] == uuid[:14]
                            for b in lolmlat
                        )
                        else T.No
                    )
                    self._last_check = datetime.now()

                else:
                    print_err(f"adsblol returned status {status}")
        if self._agg == "flyitaly":
            # get the data from json
            json_url = "https://my.flyitalyadsb.com/am_i_feeding"
            response_dict, status = self.get_json(json_url)
            if response_dict and status == 200:
                feeding = response_dict["feeding"]
                if feeding:
                    self._beast = T.Yes if feeding.get("beast") else T.No
                    self._mlat = T.Yes if feeding.get("mlat") else T.No
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
            # we are having an easier time finding mlat data via the myip api
            # as apparently mlathub doesn't always send the right uuid
            json_ip_url = "https://api.adsb.fi/v1/myip"
            adsbfi_dict, status = self.get_json(json_ip_url)
            if adsbfi_dict and status == 200:
                mlat_array = adsbfi_dict.get("mlat", [])
                self._mlat = (
                    T.Yes
                    if any(m.get("user", "") == name for m in mlat_array)
                    else T.No
                )
                self._last_check = datetime.now()
            else:
                print_err(f"adsbfi v1/myip returned {status}")
            adsbfi_dict, status = self.get_json(json_uuid_url)
            if adsbfi_dict and status == 200:
                self._beast = (
                    T.Yes
                    if len(adsbfi_dict.get("beast", [])) > 0
                    and adsbfi_dict.get("beast")[0].get("receiverId") == uuid
                    else T.No
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
                    self._beast = T.Yes if rdata.get("beast") else T.No
                    self._mlat = T.Yes if rdata.get("mlat") else T.No
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
                    T.Yes
                    if fa_dict.get("adept")
                    and fa_dict.get("adept").get("status") == "green"
                    else T.No
                )
                self._mlat = (
                    T.Yes
                    if fa_dict.get("mlat")
                    and fa_dict.get("mlat").get("status") == "green"
                    else T.No
                )
                self._last_check = datetime.now()
            else:
                print_err(f"flightaware at {json_url} returned {status}")
        elif self._agg == "flightradar":
            suffix = "" if self._idx == 0 else f"_{self._idx}"
            json_url = f"{self._url}/fr24-monitor.json{suffix}"
            fr_dict, status = self.get_json(json_url)
            if fr_dict and status == 200:
                # print_err(f"fr monitor.json returned {fr_dict}")
                self._beast = (
                    T.Yes if fr_dict.get("feed_status") == "connected" else T.No
                )
                self._last_check = datetime.now()
            else:
                print_err(f"flightradar at {json_url} returned {status}")
        elif self._agg == "radarplane":
            uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
            json_url = f"https://radarplane.com/api/v1/feed/check/{uuid}"
            rp_dict, status = self.get_json(json_url)
            if rp_dict and rp_dict.get("data") and status == 200:
                self._beast = T.Yes if rp_dict["data"].get("beast") else T.No
                self._mlat = T.Yes if rp_dict["data"].get("mlat") else T.No
                self._last_check = datetime.now()
            else:
                print_err(f"radarplane returned {status}")
        elif self._agg == "radarbox":
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
                match = re.search(
                    r"This is your station serial number: ([A-Z0-9]+)", serial_text
                )
                if match:
                    station_serial = match.group(1)
                    self._d.env_by_tags(["radarbox", "sn"]).list_set(
                        self._idx, station_serial
                    )
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
                        self._beast = T.Yes if online else T.No
                        self._mlat = T.Yes if mlat_online else T.No
                        self._last_check = datetime.now()
        elif self._agg == "1090uk":
            key = self._d.env_by_tags(["1090uk", "key"]).list_get(self._idx)
            json_url = f"https://www.1090mhz.uk/mystatus.php?key={key}"
            tn_dict, status = self.get_json(json_url)
            if tn_dict and status == 200:
                online = tn_dict.get("online", False)
                self._beast = T.Yes if online else T.No
                self._last_check = datetime.now()
        elif self._agg == "alive":
            json_url = "https://api.airplanes.live/feed-status"
            a_dict, status = self.get_json(json_url)
            if a_dict and status == 200:
                uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
                beast_clients = a_dict.get("beast_clients")
                # print_err(f"alife returned {beast_clients}", level=8)
                if beast_clients:
                    self._beast = (
                        T.Yes
                        if any(bc.get("uuid") == uuid for bc in beast_clients)
                        else T.No
                    )
                mlat_clients = a_dict.get("mlat_clients")
                # print_err(f"alife returned {mlat_clients}")
                if mlat_clients:
                    self._mlat = (
                        T.Yes
                        if any(
                            isinstance(mc.get("uuid"), list)
                            and mc.get("uuid")[0] == uuid
                            for mc in mlat_clients
                        )
                        else T.No
                    )
                self._last_check = datetime.now()
            else:
                print_err(f"airplanes.james returned {status}")
        elif self._agg == "adsbx":
            # another one where we need to grab an ID from the docker logs
            if not self._d.env_by_tags("adsbxfeederid").list_get(self._idx):
                print_err(f"don't have the adsbX Feeder ID for {self._idx}, yet")
                container_name = (
                    "ultrafeeder"
                    if self._idx == 0
                    else f"ultrafeeder_stage2_{self._idx}"
                )
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
                    r"www.adsbexchange.com/api/feeders/\?feed=([0-9a-zA-Z]*)",
                    output,
                )
                if match:
                    adsbx_id = match.group(1)
                else:
                    print_err(
                        f"ran: docker logs {container_name} | grep 'www.adsbexchange.com/api/feeders' | tail -1"
                    )
                    print_err(f"failed to find adsbx ID in response {output}")
                    return
                self._d.env_by_tags("adsbxfeederid").list_set(self._idx, adsbx_id)
            # let's get the feeder status from their feed status page
            feederid = self._d.env_by_tags("adsbxfeederid").list_get(self._idx)
            html_url = f"https://www.adsbexchange.com/api/feeders/?feed={feederid}"
            adsbx_text, status = self.get_plain(html_url)
            if adsbx_text and status == 200:
                match = re.search(r'"data":([^]]+])', adsbx_text)
                if match:
                    self._beast = (
                        T.No
                        if match.group(1).endswith(",0]")
                        or match.group(1).endswith('0",]')
                        else T.Yes
                    )
                else:
                    print_err(f"failed to find adsbx Status in response {adsbx_text}")
                    return
            else:
                print_err(f"adsbx returned {status}")
                return
            self._last_check = datetime.now()
            if self._beast == T.No:
                self._mlat = T.No
                return
            # now check mlat - which we can't really get easily from their status page
            # but can get from our docker logs again
            container_name = (
                "ultrafeeder" if self._idx == 0 else f"ultrafeeder_stage2_{self._idx}"
            )
            try:
                result = subprocess.run(
                    f"docker logs --since=20m {container_name} | grep '\[mlat-client]\[feed.adsbexchange.com] Results:'",
                    shell=True,
                    capture_output=True,
                    text=True,
                )
            except:
                print_err(
                    f"got exception trying to look at the adsbx docker logs from {container_name}"
                )
                return
            match = re.search(
                r".mlat-client..feed.adsbexchange.com. Results:[^0-9]*([0-9.]*) positions/minute",
                result.stdout,
            )
            if match:
                self._mlat = T.Yes if match.group(1) != "0.0" else T.No
                self._last_check = datetime.now()
            else:
                self._mlat = T.Unknown

        elif self._agg == "tat":
            # get the data from the status text site
            text_url = "https://theairtraffic.com/iapi/feeder_status"
            tat_text, status = self.get_plain(text_url)
            if text_url and status == 200:
                if re.search(r" No ADS-B feed", tat_text):
                    self._beast = T.No
                elif re.search(r"  ADS-B feed", tat_text):
                    self._beast = T.Yes
                else:
                    print_err(f"can't parse beast part of tat response")
                    return
                if re.search(r" No MLAT feed", tat_text):
                    self._mlat = T.No
                elif re.search(r"  MLAT feed", tat_text):
                    self._mlat = T.Yes
                else:
                    print_err(f"can't parse mlat part of tat response")
                    # but since we got someting we could parse for beast above, let's keep going
                self._last_check = datetime.now()
            else:
                print_err(f"tat returned {status}")
        elif self._agg == "planespotters":
            uf_uuid = self._d.env_by_tags("ultrafeeder_uuid").list_get(self._idx)
            html_url = f"https://www.planespotters.net/feed/status/{uf_uuid}"
            ps_text, status = self.get_plain(html_url)
            if ps_text and status == 200:
                self._beast = (
                    T.No if re.search("Feeder client not connected", ps_text) else T.Yes
                )
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
                self._beast = T.Yes if adsb.get("connected") else T.No
                self._mlat = T.Yes if mlat.get("connected") else T.No
                self._last_check = datetime.now()
            else:
                print_err(f"planewatch returned {status}")

    def __repr__(self):
        return f"Aggregator({self._agg} last_check: {str(self._last_check)}, beast: {self._beast} mlat: {self._mlat})"


class ImStatus:
    def __init__(self, data: Data):
        self._d = data

    def check(self):
        json_url = f"https://adsb.im/api/status"
        return generic_get_json(json_url, self._d.env_by_tags("pack").value)
