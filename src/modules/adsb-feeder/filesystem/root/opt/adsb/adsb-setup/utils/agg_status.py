import json
import re
import requests
from datetime import datetime, timedelta
from enum import Enum
from .util import print_err
from .constants import Constants

T = Enum("T", ["Yes", "No", "Unknown"])


def generic_get_json(url: str, data):
    requests.packages.urllib3.util.connection.HAS_IPV6 = False
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
    except:
        # for some reason this didn't work
        print_err("checking {url} failed: reason unknown")
    else:
        return response.json()
    return None


class AggStatus:
    def __init__(self, agg: str, constants: Constants, url: str):
        self._agg = agg
        self._last_check = datetime.fromtimestamp(0.0)
        self._beast = T.Unknown
        self._mlat = T.Unknown
        self._constants = constants
        self._url = url
        self.check()

    @property
    def beast(self) -> str:
        now = datetime.now()
        if now - self._last_check < timedelta(minutes=5.0):
            return "+" if self._beast == T.Yes else "-" if self._beast == T.No else "."
        self.check()
        if now - self._last_check < timedelta(minutes=5.0):
            return "+" if self._beast == T.Yes else "-" if self._beast == T.No else "."
        return "."

    @property
    def mlat(self) -> str:
        now = datetime.now()
        if now - self._last_check < timedelta(minutes=5.0):
            return "+" if self._mlat == T.Yes else "-" if self._mlat == T.No else "."
        self.check()
        if now - self._last_check < timedelta(minutes=5.0):
            return "+" if self._mlat == T.Yes else "-" if self._mlat == T.No else "."
        return "."

    def get_json(self, json_url):
        return generic_get_json(json_url, None)

    def get_plain(self, plain_url):
        requests.packages.urllib3.util.connection.HAS_IPV6 = False
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
            print_err(f"checking {url} failed: {err}")
        except:
            # for some reason this didn't work
            print_err("checking {url} failed: reason unknown")
        else:
            return response.text
        return None

    def check(self):
        # figure out the feeder state at this aggregator (if possible)
        if self._agg == "adsblol":
            json_url = "https://api.adsb.lol/0/me"
            response_dict = self.get_json(json_url)
            if response_dict:
                self._beast = T.Yes if len(response_dict["clients"]["beast"]) else T.No
                self._mlat = T.Yes if len(response_dict["clients"]["mlat"]) else T.No
                self._last_check = datetime.now()
        if self._agg == "flyitaly":
            # get the data from json
            json_url = "https://my.flyitalyadsb.com/am_i_feeding"
            response_dict = self.get_json(json_url)
            if response_dict:
                feeding = response_dict["feeding"]
                self._beast = T.Yes if feeding["beast"] else T.No
                self._mlat = T.Yes if feeding["mlat"] else T.No
                self._last_check = datetime.now()
        elif self._agg == "adsbfi":
            # get the data from json
            json_url = "https://api.adsb.fi/v1/myip"
            adsbfi_dict = self.get_json(json_url)
            if adsbfi_dict:
                # print_err(f"adsbfi returned {adsbfi_dict}")
                self._beast = T.No if adsbfi_dict["beast"] == [] else T.Yes
                self._mlat = T.No if adsbfi_dict["mlat"] == [] else T.Yes
                self._last_check = datetime.now()
        elif self._agg == "radarplane":
            json_url = "https://radarplane.com/api/v1/feed/check"
            radarplane_dict = self.get_json(json_url)
            if radarplane_dict:
                # print_err(f"radarplane returned {radarplane_dict}")
                self._beast = T.Yes if radarplane_dict["data"]["beast"] else T.No
                self._mlat = T.Yes if radarplane_dict["data"]["mlat"] else T.No
                self._last_check = datetime.now()
        elif self._agg == "flightaware":
            json_url = f"{self._url}/fa-status.json/"
            fa_dict = self.get_json(json_url)
            if fa_dict:
                # print_err(f"fa status.json returned {fa_dict}")
                self._beast = T.Yes if fa_dict["adept"]["status"] == "green" else T.No
                self._mlat = T.Yes if fa_dict["mlat"]["status"] == "green" else T.No
                self._last_check = datetime.now()
        elif self._agg == "flightradar":
            json_url = f"{self._url}/fr24-monitor.json"
            fr_dict = self.get_json(json_url)
            if fr_dict:
                # print_err(f"fr monitor.json returned {fr_dict}")
                self._beast = T.Yes if fr_dict["feed_status"] == "connected" else T.No
                self._last_check = datetime.now()
        elif self._agg == "radarplane":
            uuid = self._constants.env_by_tags("ultrafeeder_uuid").value
            json_url = f"https://radarplane.com/api/v1/feed/check/{uuid}"
            rp_dict = self.get_json(json_url)
            if rp_dict:
                self._beast = T.Yes if rp_dict["data"]["beast"] else T.No
                self._mlat = T.Yes if rp_dict["data"]["mlat"] else T.No
                self._last_check = datetime.now()
        elif self._agg == "alive":
            json_url = "https://api.airplanes.live/feed-status"
            a_dict = self.get_json(json_url)
            if a_dict:
                uuid = self._constants.env_by_tags("ultrafeeder_uuid").value
                self._beast = (
                    T.Yes
                    if any({bc["rId"] == uuid for bc in a_dict["beast_clients"]})
                    else T.No
                )
                self._mlat = (
                    T.Yes
                    if any({mc["uuid"][0] == uuid for mc in a_dict["mlat_clients"]})
                    else T.No
                )
                self._last_check = datetime.now()
        elif self._agg == "adsbx":
            html_url = "https://www.adsbexchange.com/myip/"
            adsbx_text = self.get_plain(html_url)
            if adsbx_text:
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
                    self._constants.env_by_tags("adsbxfeederid").value = match.group(1)
        elif self._agg == "tat":
            # get the data from the status text site
            text_url = "https://theairtraffic.com/iapi/feeder_status"
            tat_text = self.get_plain(text_url)
            if text_url:
                # print_err(f"tat returned {tat_text}")
                if re.search(r" No ADS-B feed", tat_text):
                    self._beast = T.No
                elif re.search(r"  ADS-B feed", tat_text):
                    self._beast = T.Yes
                else:
                    print_err(f"can't parse beast part of tat response {tat_text}")
                    return
                if re.search(r" No MLAT feed", tat_text):
                    self._mlat = T.No
                elif re.search(r"  MLAT feed", tat_text):
                    self._mlat = T.Yes
                else:
                    print_err(f"can't parse mlat part of tat response {tat_text}")
                    # but since we got someting we could parse for beast above, let's keep going
                self._last_check = datetime.now()
        elif self._agg == "planespotters":
            uf_uuid = self._constants.env_by_tags("ultrafeeder_uuid").value
            html_url = f"https://www.planespotters.net/feed/status/{uf_uuid}"
            ps_text = self.get_plain(html_url)
            if ps_text:
                self._beast = (
                    T.No if re.search("Feeder client not connected", ps_text) else T.Yes
                )
                self._last_check = datetime.now()
        elif self._agg == "planewatch":
            pw_uuid = self._constants.env_by_tags(
                ["planewatch", "key"]
            ).value  # they sometimes call it key, sometimes uuid
            if not pw_uuid:
                return
            json_url = f"https://atc.plane.watch/api/v1/feeders/{pw_uuid}/status.json"
            pw_dict = self.get_json(json_url)
            if pw_dict:
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

    def __repr__(self):
        return f"Aggregator({self._agg} last_check: {str(self._last_check)}, beast: {self._beast} mlat: {self._mlat})"


class ImStatus:
    def __init__(self, constants: Constants):
        self._constants = constants

    def check(self):
        json_url = f"https://adsb.im/api/status"
        return generic_get_json(json_url, self._constants.env_by_tags("pack").value)
