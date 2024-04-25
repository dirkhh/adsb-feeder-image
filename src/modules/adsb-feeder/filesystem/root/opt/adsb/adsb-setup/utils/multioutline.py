import json
from shapely.geometry import LinearRing, Polygon
from shapely.ops import unary_union


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
            polygons.append(
                Polygon(shell=LinearRing(data[i]["actualRange"]["last24h"]["points"]))
            )
        made_change = True
        look_at = range(1, len(data))
        while made_change:
            made_change = False
            to_consider = [0]
            for i in look_at:
                combined = False
                for j in to_consider:
                    if polygons[j].disjoint(polygons[i]):
                        print(f"polygon {i} disjoint {j}")
                    else:
                        print(f"combine polygons {i} and {j}")
                        p = unary_union([polygons[j], polygons[i]])
                        polygons[j] = p
                        made_change = True
                        combined = True
                if not combined:
                    to_consider.append(i)
            look_at = to_consider[1:]
        for i in to_consider:
            points = [[x, y] for x, y, a in polygons[i].exterior.coords]
            result["multiRange"].append(points)
        return result
