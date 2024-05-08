import json
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

    def create(self, num):
        data = self._get_outlines(num)
        result = {"multiRange": []}
        polygons = []
        for i in range(len(data)):
            if len(data[i]["actualRange"]["last24h"]["points"]) > 2:
                try:
                    p = Polygon(
                        shell=LinearRing(data[i]["actualRange"]["last24h"]["points"])
                    )
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
                        pass
                if not combined:
                    to_consider.append(i)
            look_at = to_consider[1:]
        for i in to_consider:
            try:
                points = [[x, y] for x, y, a in polygons[i].exterior.coords]
                result["multiRange"].append(points)
            except:
                pass
        return result
