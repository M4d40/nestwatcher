import json
import requests
import random
import math

from shapely import geometry
from shapely.ops import polylabel, linemerge, unary_union, polygonize
from datetime import datetime
from geojson import Feature
from urllib.parse import quote_plus

from utils.logging import log

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
    def __init__(self, area, settings={}):
        self.name = area["name"]
        self.settings = settings
        self.nests = []

        sql_fence = []
        polygon_ = []
        fence = area["path"]

        for lat, lon in fence:
            polygon_.append((lon, lat))
            sql_fence.append(f"{lat} {lon}")
        sql_fence.append(f"{fence[0][0]} {fence[0][1]}")
        
        self.polygon = geometry.Polygon(polygon_)
        self.sql_fence = "(" + ",".join(sql_fence) + ")"

        bounds = self.polygon.bounds
        self.bbox = f"{bounds[1]},{bounds[0]},{bounds[3]},{bounds[2]}"
    
    def get_nest_text(self, config, emote_refs=None):
        with open(f"data/mon_names/{config.language}.json", "r") as f:
            mon_names = json.load(f)
        with open("config/discord.json", "r") as f:
            template = json.load(f)
        try:
            with open("data/custom_emotes.json", "r") as f:
                emote_data = json.load(f)
        except:
            emote_data = {
                "Shiny": "✨",
                "Grass": "🌿",
                "Poison": "☠",
                "Fire": "🔥",
                "Flying": "🐦",
                "Water": "💧",
                "Bug": "🐛",
                "Normal": "⭕",
                "Dark": "🌑",
                "Electric": "⚡",
                "Rock": "🗿",
                "Ground": "🌍",
                "Fairy": "🦋",
                "Fighting": "👊",
                "Psychic": "☯",
                "Steel": "🔩",
                "Ice": "❄",
                "Ghost": "👻",
                "Dragon": "🐲"
            }
            with open("data/custom_emotes.json", "w+") as f:
                f.write(json.dumps(emote_data, indent=4))
        shiny_data = requests.get("https://pogoapi.net/api/v1/shiny_pokemon.json").json()
        type_data_raw = requests.get("https://pogoapi.net/api/v1/pokemon_types.json").json()

        type_data = {}
        for data in type_data_raw:
            if data.get("form", "").lower() == "normal":
                type_data[int(data.get("pokemon_id", 0))] = data.get("type", [])

        filters = template[1]
        entries = ""
        entry_list = []

        # Sorting

        def sort_avg(nest):
            return nest.mon_avg
        def sort_count(nest):
            return nest.mon_count
        def sort_ratio(nest):
            return nest.mon_ratio
        def sort_mid(nest):
            return nest.mon_id
        def sort_name(nest):
            return nest.name

        sorts = {
            "mon_avg": [sort_avg, True],
            "mon_count": [sort_count, True],
            "mon_id": [sort_mid, False],
            "mon_ratio": [sort_ratio, True],
            "park_name": [sort_name, False]
        }
        sort_ = sorts[filters["sort_by"]]
        self.nests = sorted(self.nests, key=sort_[0], reverse=sort_[1])

        # statimap gen
        #polygons = []
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
            def add_to_points(points, monid, lat, lon):
                points.append([
                    str(monid).zfill(3),
                    round(lat, 6),
                    round(lon, 6)
                ])
                return points
            for nest in self.nests:
                points = []
                if self.settings["max_markers"] == 1:
                    points = add_to_points(points, nest.mon_id, nest.lat, nest.lon)
                else:
                    if nest.mon_avg > self.settings["max_markers"]:
                        avg = self.settings["max_markers"]
                    else:
                        avg = round(nest.mon_avg)
                    while len(points) <= avg - 1:
                        pnt = geometry.Point(random.uniform(nest.min_lon, nest.max_lon), random.uniform(nest.min_lat, nest.max_lat))
                        if nest.polygon.contains(pnt):
                            points = add_to_points(points, nest.mon_id, pnt.y, pnt.x)
                markers += points
            center_lat = minlat + ((maxlat - minlat) / 2)
            center_lon = minlon + ((maxlon - minlon) / 2)
            def parse(var):
                return quote_plus(json.dumps(var)).replace('+','')
            
            static_map_data = {
                "lat": center_lat,
                "lon": center_lon,
                "zoom": zoom,
                "nestjson": markers
            }
            static_map_raw = config.static_url + "staticmap/nests?pregenerate=true&regeneratable=true"
            result = requests.post(static_map_raw, json=static_map_data)
            if "error" in result.text:
                log.error(f"Error while generating Static Map:\n\n{static_map_raw}\n{result.text}\n")
                static_map = ""
            else:
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
                        staticmap=static_map,
                        current_time=datetime.utcnow()
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
                shiny_emote = emote_data.get("Shiny", "")

            type_emotes = []
            types = type_data.get(nest.mon_id)
            for t in types:
                type_emotes.append(emote_data.get(t, ""))
            type_emote = "/".join(type_emotes)

            mon_emote = ""
            if emote_refs is not None:
                emote_id = emote_refs.get(nest.mon_id, "")
                if not emote_id == "":
                    mon_emote = f"<:m{nest.mon_id}:{emote_id}>"

            entry = filters["nest_entry"].format(
                park_name=nest.name,
                lat=nest.lat,
                lon=nest.lon,

                mon_id=nest.mon_id,
                mon_avg=nest.mon_avg,
                mon_count=nest.mon_count,
                mon_ratio=nest.mon_ratio*100,
                mon_name=mon_names.get(str(nest.mon_id), ""),
                mon_emoji=mon_emote,
                type_emoji=type_emote,
                shiny=shiny_emote
            )
            if len(entries) + len(entry) <= 2048:
                entries += entry
            entry_list.append(entry)
        return replace(template[0]), entry_list

class Park():
    def __init__(self, element, config):
        self._element = element
        self._default_name = config.default_park_name
        self._config = config

        self.polygon = None
        self.min_lon, self.min_lat, self.max_lon, self.max_lat = (0, 0, 0, 0)
        self.sql_fence = ""
        self.feature = None
        self.path = []

        self.id = element["id"]
        self.name = ""
        self.lat = 0
        self.lon = 0
        self.connect = []

        self.mon_id = 0
        self.mon_form = 0
        self.mon_count = 0
        self.mon_avg = 0
        self.mon_ratio = 0

        self.is_valid = True

    def mon_data(self, mid, amount, hours, spawns):
        self.mon_id = mid
        self.mon_count = amount
        self.mon_avg = round(
                (amount / float(hours)) * (
                    24.00 / float(self._config.hours_since_change)), 2)
        self.mon_ratio = self.mon_avg / spawns

    def generate_details(self, area_file, nr):
        if self.id in area_file.keys():
            entry = area_file[self.id]
            self.name = entry["name"]
            self.lat = round(float(entry["center"][0]), 6)
            self.lon = round(float(entry["center"][1]), 6)
        else:
            tags = self._element.get("tags", {})
            self.name = tags.get("name", tags.get("official_name", self._default_name.format(nr=nr)))
            # get name. if not there, get official name. if not there, use default name

            if isinstance(self.polygon, geometry.MultiPolygon):
                center_point = self.polygon.centroid
            else:
                center_point = polylabel(self.polygon, tolerance=1e-6)
            self.lat = round(center_point.y, 6)
            self.lon = round(center_point.x, 6)

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
        path = []
        for lon, lat in self.polygon.exterior.coords:
            sql_fence.append(f"{lat} {lon}")
            path.append([lat, lon])
        self.path = [path]
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
                continue
            else:
                way = way[0]
            new_ways.append(way.id)

            area_points = list()
            for point in way._element["nodes"]:
                point_coords = nodes[point]
                area_points.append([point_coords['lon'], point_coords['lat']])

            way_poly = geometry.LineString(area_points)

            if member["role"] == "inner":
                inner_members.append(way_poly)
            else:
                outer_members.append(way_poly)

        def get_polys(lss):
            merged = linemerge([*lss])
            borders = unary_union(merged)
            polygons = list(polygonize(borders))
            return polygons

        outer_polygon = geometry.MultiPolygon(get_polys(outer_members))
        inner_polygon = geometry.MultiPolygon(get_polys(inner_members))
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
            path = []
            if polygon.is_valid:
                coords = polygon.exterior.coords
                for lon, lat in coords:
                    sql_fence.append(f"{lat} {lon}")
                    path.append([lat, lon])
                self.path.append(path)
                sql_fences.append("(" + ",".join(sql_fence) + ")")
        self.sql_fence = ",".join(sql_fences)

        return new_ways