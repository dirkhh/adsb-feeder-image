import json
import os
import subprocess
import time
from shapely.geometry import LinearRing, Polygon
from shapely.ops import unary_union

use_is_valid_reason = True
try:
    from shapely.validation import is_valid_reason
except:
    use_is_valid_reason = False


class MultiOutline:
    def _get_outlines(self, num):
        data = []
        for i in range(1, num + 1):
            try:
                outline = json.load(
                    open(f"/run/adsb-feeder-ultrafeeder_{i}/readsb/outline.json")
                )
            except:
                pass
            else:
                data.append(outline)
        return data

    def _get_heywhatsthat(self, num):
        data = []
        now = time.time()
        os.makedirs("/opt/adsb/data", exist_ok=True)
        for i in range(1, num + 1):
            if (
                not os.path.exists(f"/opt/adsb/data/heywhatsthat_{i}.json")
                or os.path.getmtime(f"/opt/adsb/data/heywhatsthat_{i}.json")
                < now - 3600
            ):
                if True:  # try:
                    subprocess.run(
                        f"docker cp  ultrafeeder_stage2_{i}:/usr/local/share/tar1090/html-webroot/upintheair.json /opt/adsb/data/heywhatsthat_{i}.json",
                        shell=True,
                        check=True,
                    )
                # except:
                #    pass
            if True:  # try:
                hwt = json.load(open(f"/opt/adsb/data/heywhatsthat_{i}.json"))
                # except:
                #    pass
                # else:
                data.append(hwt)
        return data

    def create_outline(self, num):
        data = self._get_outlines(num)
        return self.create(data)

    def create_heywhatsthat(self, num):
        data = self._get_heywhatsthat(num)
        result = {
            "id": "combined",
            "lat": data[0]["lat"],
            "lon": data[0]["lon"],
            "rings": [],
            "refraction": "0.25",
        }
        for idx in range(len(data[0]["rings"])):
            alt = data[0]["rings"][idx]["alt"]
            multi_range = self.create(data, hwt_alt=alt).get("multiRange")
            for i in range(len(multi_range)):
                # r = [{"points": p, "alt": alt} for p in multi_range[i]]
                result["rings"].append({"points": multi_range[i], "alt": alt})
        return result

    def create(self, data, hwt_alt=0):
        result = {"multiRange": []}
        polygons = []
        for i in range(len(data)):
            d = data[i]
            if hwt_alt == 0:
                if d.get("actualRange"):
                    points = d["actualRange"]["last24h"]["points"]
                else:
                    print(f"can't get points from outline #{i}: {d}")
                    points = []
            else:
                points = [r["points"] for r in d["rings"] if r["alt"] == hwt_alt][0]
            if len(points) > 2:
                try:
                    p = Polygon(shell=LinearRing(points))
                    if p:
                        if use_is_valid_reason:
                            r = is_valid_reason(p)
                            if r == "Valid Geometry":
                                polygons.append(p)
                            else:
                                print(f"can't create polygon from outline #{i} - {r}")
                        else:
                            try:
                                polygons.append(p)
                            except:
                                print(f"can't create polygon from outline #{i}")
                    else:
                        print(f"can't create polygon from outline #{i}")
                except:
                    print(
                        f"can't create linear ring from outline #{i} - maybe there is no data, yet?"
                    )
        made_change = True
        look_at = range(1, len(polygons))
        while made_change:
            made_change = False
            to_consider = [0]
            for i in look_at:
                combined = False
                for j in to_consider:
                    try:
                        if not polygons[j].disjoint(polygons[i]):
                            p = unary_union([polygons[j], polygons[i]])
                            polygons[j] = p
                            made_change = True
                            combined = True
                    except:
                        print(f"exception while combining polygons #{j} and #{i}")
                        pass
                if not combined:
                    to_consider.append(i)
            look_at = to_consider[1:]
        for i in to_consider:
            try:
                if hwt_alt == 0:
                    points = [[x, y] for x, y, a in polygons[i].exterior.coords]
                else:
                    points = [[x, y] for x, y in polygons[i].exterior.coords]
                result["multiRange"].append(points)
            except:
                print(f"can't get points from polygon #{i} exterior coords")
                pass
        return result
