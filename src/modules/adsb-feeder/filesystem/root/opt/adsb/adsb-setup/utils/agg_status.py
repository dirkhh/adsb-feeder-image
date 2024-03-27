import json
import re
import subprocess
import requests
from datetime import datetime, timedelta
from enum import Enum
from .util import print_err
from .data import Data

T = Enum("T", ["Yes", "No", "Unknown"])


def generic_get_json(url: str, data):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False
    status = -1
    try:
        response = requests.request(
            method="GET" if data == None else "POST",
            url=url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "ADS-B Image",
            },
        )
    except (
        requests.HTTPError,
        requests.ConnectionError,
        requests.Timeout,
        requests.RequestException,
    ) as err:
        print_err(f"checking {url} failed: {err}")
        status = err.errno
    except:
        # for some reason this didn't work
        print_err("checking {url} failed: reason unknown")
    else:
        return response.json(), response.status_code
    return None, status


class AggStatus:
    def __init__(self, agg: str, d: Data, url: str):
        self._agg = agg
        self._last_check = datetime.fromtimestamp(0.0)
        self._beast = T.Unknown
        self._mlat = T.Unknown
        self._d = d
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
            json_url = "https://api.adsb.lol/0/me"
            response_dict, status = self.get_json(json_url)
            if response_dict and status == 200:
                lolclients = response_dict.get("clients")
                if lolclients:
                    lolbeast = lolclients.get("beast")
                    lolmlat = lolclients.get("mlat")
                    self._beast = (
                        T.Yes if isinstance(lolbeast, list) and len(lolbeast) else T.No
                    )
                    self._mlat = (
                        T.Yes if isinstance(lolmlat, list) and len(lolmlat) else T.No
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
            json_url = "https://api.adsb.fi/v1/myip"
            adsbfi_dict, status = self.get_json(json_url)
            if adsbfi_dict and status == 200:
                self._beast = T.No if adsbfi_dict.get("beast") == [] else T.Yes
                self._mlat = T.No if adsbfi_dict.get("mlat") == [] else T.Yes
                self._last_check = datetime.now()
            else:
                print_err(f"adsbfi returned {status}")
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
            json_url = f"{self._url}/fa-status.json/"
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
                print_err(f"flightaware returned {status}")
        elif self._agg == "flightradar":
            json_url = f"{self._url}/fr24-monitor.json"
            fr_dict, status = self.get_json(json_url)
            if fr_dict and status == 200:
                # print_err(f"fr monitor.json returned {fr_dict}")
                self._beast = (
                    T.Yes if fr_dict.get("feed_status") == "connected" else T.No
                )
                self._last_check = datetime.now()
            else:
                print_err(f"flightradar returned {status}")
        elif self._agg == "radarplane":
            uuid = self._d.env_by_tags("ultrafeeder_uuid").value
            json_url = f"https://radarplane.com/api/v1/feed/check/{uuid}"
            rp_dict, status = self.get_json(json_url)
            if rp_dict and rp_dict.get("data") and status == 200:
                self._beast = T.Yes if rp_dict["data"].get("beast") else T.No
                self._mlat = T.Yes if rp_dict["data"].get("mlat") else T.No
                self._last_check = datetime.now()
            else:
                print_err(f"radarplane returned {status}")
        elif self._agg == "radarbox":
            station_serial = self._d.env_by_tags(["radarbox", "sn"]).value
            if not station_serial:
                # dang, I hate this part
                try:
                    result = subprocess.run(
                        "docker logs rbfeeder | grep 'station serial number' | tail -1",
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
                    self._d.env_by_tags(["radarbox", "sn"]).value = station_serial
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
            key = self._d.env_by_tags(["1090uk", "key"]).value
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
                uuid = self._d.env_by_tags("ultrafeeder_uuid").value
                beast_clients = a_dict.get("beast_clients")
                if beast_clients:
                    self._beast = (
                        T.Yes
                        if any({bc.get("uuid") == uuid for bc in beast_clients})
                        else T.No
                    )
                mlat_clients = a_dict.get("mlat_clients")
                if mlat_clients:
                    self._mlat = (
                        T.Yes
                        if any(
                            {
                                isinstance(mc.get("uuid"), list)
                                and mc.get("uuid")[0] == uuid
                                for mc in mlat_clients
                            }
                        )
                        else T.No
                    )
                self._last_check = datetime.now()
            else:
                print_err(f"airplanes.james returned {status}")
        elif self._agg == "adsbx":
            html_url = "https://www.adsbexchange.com/myip/"
            adsbx_text, status = self.get_plain(html_url)
            if adsbx_text and status == 200:
                match = re.search(r"<.*?>([a-zA-Z ]*)<.*?>ADS-B Status", adsbx_text)
                if match:
                    self._beast = (
                        T.Yes if match.group(1).find("Feed Ok") != -1 else T.No
                    )
                else:
                    print_err("failed to find adsbx Status in response")
                    return
                match = re.search(r"<.*?>([a-zA-Z ]*)<.*?>MLAT Status", adsbx_text)
                if match:
                    self._mlat = T.Yes if match.group(1).find("Feed Ok") != -1 else T.No
                self._last_check = datetime.now()
                match = re.search(
                    r'placeholder="([^"]+)" aria-label="Feed UID"', adsbx_text
                )
                if match:
                    self._d.env_by_tags("adsbxfeederid").value = match.group(1)
            else:
                print_err(f"adsbx returned {status}")
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
            uf_uuid = self._d.env_by_tags("ultrafeeder_uuid").value
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
            pw_uuid = self._d.env_by_tags(
                ["planewatch", "key"]
            ).value  # they sometimes call it key, sometimes uuid
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
    def __init__(self, d: Data):
        self._d = d

    def check(self):
        json_url = f"https://adsb.im/api/status"
        return generic_get_json(json_url, self._d.env_by_tags("pack").value)
