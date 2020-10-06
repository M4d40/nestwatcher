import json
import requests
import random
import math

from shapely import geometry
from shapely.ops import polylabel
from geojson import Feature
from urllib.parse import quote_plus

def get_zoom(ne, sw, width, height, tile_size):
    ne = [c * 1.06 for c in ne]
    sw = [c * 1.06 for c in sw]

    if ne == sw:
        return 17.5

    def latRad(lat):
        sin = math.sin(lat * math.pi / 180)
        rad = math.log((1 + sin) / (1 - sin)) / 2
        return max(min(rad, math.pi), -math.pi) / 2

    def zoom(px, tile, fraction):
        return round(math.log((px / tile / fraction), 2), 2)

    lat_fraction = (latRad(ne[0]) - latRad(sw[0])) / math.pi

    angle = ne[1] - sw[1] 
    if angle < 0:
        angle += 360
    lon_fraction = angle / 360

    lat_zoom = zoom(height, tile_size, lat_fraction)
    lon_zoom = zoom(width, tile_size, lon_fraction)

    return min(lat_zoom, lon_zoom)

class Area():
    def __init__(self, area, settings):
        self.name = area["name"]
        self.settings = settings
        self.nests = []

        sql_fence = []
        polygon_ = []
        fence = area["path"]

        for lat, lon in fence:
            polygon_.append((lon, lat))
            sql_fence.append(f"{lat} {lon}")
        
        self.polygon = geometry.Polygon(polygon_)
        self.sql_fence = ",".join(sql_fence)

        bounds = self.polygon.bounds
        self.bbox = f"{bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]}"
    
    def get_nest_text(self, config, emote_refs):
        with open(f"data/mon_names/{config.language}.json", "r") as f:
            mon_names = json.load(f)
        with open("config/discord.json", "r") as f:
            template = json.load(f)
        shiny_data = requests.get("https://pogoapi.net/api/v1/shiny_pokemon.json").json()

        filters = template[1]
        entries = ""

        # Sorting

        def sort_avg(nest):
            return nest.mon_avg
        def sort_count(nest):
            return nest.mon_count
        def sort_mid(nest):
            return nest.mon_id
        def sort_name(nest):
            return nest.name

        sorts = {
            "mon_avg": [sort_avg, True],
            "mon_count": [sort_count, True],
            "mon_id": [sort_mid, False],
            "park_name": [sort_name, False]
        }
        sort_ = sorts[filters["sort_by"]]
        self.nests = sorted(self.nests, key=sort_[0], reverse=sort_[1])

        # statimap gen
        #polygons = [] # maybe?
        markers = []
        static_map = ""
        if len(config.static_url) > 0:
            maxlat = max([n.max_lat for n in self.nests])
            minlat = min([n.min_lat for n in self.nests])
            maxlon = max([n.max_lon for n in self.nests])
            minlon = min([n.min_lon for n in self.nests])
            zoom = get_zoom(
                [maxlat, maxlon],
                [minlat, minlon],
                1000,
                600,
                256
            )
            for nest in self.nests:
                points = []
                if nest.mon_avg > config.max_markers:
                    avg = config.max_markers
                else:
                    avg = round(nest.mon_avg)
                while len(points) < avg - 1:
                    pnt = geometry.Point(random.uniform(nest.min_lon, nest.max_lon), random.uniform(nest.min_lat, nest.max_lat))
                    if nest.polygon.contains(pnt):
                        points.append([
                            str(nest.mon_id).zfill(3),
                            round(pnt.y, 6),
                            round(pnt.x, 6)
                        ])
                markers += points
            center_lat = minlat + ((maxlat - minlat) / 2)
            center_lon = minlon + ((maxlon - minlon) / 2)
            static_map = config.static_url + "staticmap/nests?" + f"lat={center_lat}&lon={center_lon}&zoom={zoom}&nestjson={quote_plus(json.dumps(markers)).replace('+','')}&pregenerate=true&regeneratable=true"
            print(static_map)
            result = requests.get(static_map)
            static_map = config.static_url + f"staticmap/pregenerated/{result.text}"
            requests.get(static_map)

        # Text gen + filtering

        def replace(dic):
            # Formats all strings in a dict
            for k, v in dic.items():
                if isinstance(v, str):
                    dic[k] = v.format(
                        nest_entry=entries,
                        areaname=self.name,
                        staticmap=static_map
                    )
                elif isinstance(v, dict):
                    dic[k] = replace(v)
            return dic

        for nest in self.nests:
            if nest.mon_avg < filters["min_avg"]:
                continue
            if nest.name == nest._default_name and filters["ignore_unnamed"]:
                continue

            shiny_emote = ""
            if shiny_data.get(str(nest.mon_id), {}).get("found_wild", False):
                shiny_emote = "✨"

            mon_emote = ""
            emote_id = emote_refs.get(nest.mon_id, "")
            if not emote_id == "":
                mon_emote = f"<:m{nest.mon_id}:{emote_id}>"

            if len(entries) < 1500:
                entries += filters["nest_entry"].format(
                    park_name=nest.name,
                    lat=nest.lat,
                    lon=nest.lon,

                    mon_id=nest.mon_id,
                    mon_avg=nest.mon_avg,
                    mon_count=nest.mon_count,
                    mon_name=mon_names.get(str(nest.mon_id), ""),
                    mon_emoji=mon_emote,
                    shiny=shiny_emote
                )
        return replace(template[0])

class Park():
    def __init__(self, element, config):
        self._element = element
        self._default_name = config.default_park_name
        self._config = config

        self.polygon = None
        self.min_lon, self.min_lat, self.max_lon, self.max_lat = (0, 0, 0, 0)
        self.sql_fence = ""
        self.Feature = None

        self.id = element["id"]
        self.name = ""
        self.lat = 0
        self.lon = 0

        self.mon_id = 0
        self.mon_count = 0
        self.mon_avg = 0

        self.is_valid = True

    def mon_data(self, mid, amount, hours):
        self.mon_id = mid
        self.mon_count = amount
        self.mon_avg = round(
                (amount / float(self._config.hours_since_change)) * (
                    24.00 / float(hours)), 2)

    def generate_details(self, area_file):
        if self.id in area_file.keys():
            entry = area_file[self.id]
            self.name = entry["name"]
            self.lat = float(entry["center_lat"])
            self.lon = float(entry["center_lon"])
        else:
            tags = self._element.get("tags", {})
            self.name = tags.get("name", tags.get("official_name", self._default_name))
            # get name. if not there, get official name. if not there, use default name

            if isinstance(self.polygon, geometry.MultiPolygon):
                center_point = self.polygon.centroid
            else:
                center_point = polylabel(self.polygon, tolerance=1e-6)
            self.lat = center_point.y
            self.lon = center_point.x

        self.get_feature()

    def get_feature(self):
        self.min_lon, self.min_lat, self.max_lon, self.max_lat = self.polygon.convex_hull.bounds
        properties = {
            "name": self.name,
            "stroke": self._config.json_stroke,
            "stroke-width": self._config.json_stroke_width,
            "stroke-opacity": self._config.json_stroke_opacity,
            "fill": self._config.json_fill,
            "fill-opacity": self._config.json_fill_opacity,
            "area_center_point": geometry.Point(self.lat, self.lon),
            "min_lon": self.min_lon,
            "min_lat": self.min_lat,
            "max_lon": self.max_lon,
            "max_lat": self.max_lat,
        }

        self.feature = Feature(
            geometry=self.polygon,
            id=self.id,
            properties=properties
        )

class WayPark(Park):
    def __init__(self, element, config):
        super().__init__(element, config)
    
    def get_polygon(self, nodes):
        way_points = list()
        for point in self._element['nodes']:
            point_coords = nodes[point]
            way_points.append([point_coords['lon'], point_coords['lat']])
        if len(way_points) < 3:
            self.is_valid = False
            return
        self.polygon = geometry.Polygon(way_points)

        sql_fence = []
        for lon, lat in self.polygon.exterior.coords:
            sql_fence.append(f"{lat} {lon}")
        self.sql_fence = "(" + ",".join(sql_fence) + ")"

class RelPark(Park):
    def __init__(self, element, config):
        super().__init__(element, config)

    def get_polygon(self, nodes, ways, new_ways):
        inner_members = list()
        outer_members = list()
        for member in self._element["members"]:
            if member["type"] == "node":
                continue
            
            way = [w for w in ways if w.id == member["ref"]]
            if way == []:
                self.is_valid = False
                continue
            else:
                way = way[0]
            new_ways.append(way.id)

            area_points = list()
            for point in way._element["nodes"]:
                point_coords = nodes[point]
                area_points.append([point_coords['lon'], point_coords['lat']])
            if len(area_points) < 3:
                continue
            way_poly = geometry.Polygon(area_points)

            if member["role"] == "inner":
                inner_members.append(way_poly)
            else:
                outer_members.append(way_poly)
        outer_polygon = geometry.MultiPolygon(outer_members).buffer(0)
        inner_polygon = geometry.MultiPolygon(inner_members).buffer(0)
        final_polygon = None
        if outer_polygon and inner_polygon:
            final_polygon = outer_polygon.symmetric_difference(
                inner_polygon).difference(inner_polygon)
        elif outer_polygon:
            final_polygon = outer_polygon
        elif inner_polygon:
            final_polygon = inner_polygon
        else:
            self.is_valid = False
            final_polygon = geometry.Polygon([[0, 0], [0, 0], [0, 0]])

        self.polygon = final_polygon

        if isinstance(self.polygon, geometry.MultiPolygon):
            polygons = list(self.polygon)
        else:
            polygons = [self.polygon]

        sql_fences = []
        for polygon in polygons:
            sql_fence = []
            if polygon.is_valid:
                coords = polygon.exterior.coords
                for lon, lat in coords:
                    sql_fence.append(f"{lat} {lon}")
                first_point = f"{coords[0][1]} {coords[0][0]}"
                if first_point != sql_fence[0]:
                    sql_fence.append(first_point)
                sql_fences.append("(" + ",".join(sql_fence) + ")")
        self.sql_fence = ",".join(sql_fences)

        return new_ways