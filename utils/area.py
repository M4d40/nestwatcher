from shapely import geometry
from shapely.ops import polylabel
from geojson import Feature

class Area():
    def __init__(self, area, settings):
        self.name = area["name"]
        self.settings = settings
        self.nests = []

        sql_fence = []
        polygon_ = []
        fence = area["path"]

        for lat, lon in fence:
            polygon_.append((lat, lon))
            sql_fence.append(f"{lat} {lon}")
        
        self.polygon = geometry.Polygon(polygon_)
        self.sql_fence = ",".join(sql_fence)

        bounds = self.polygon.bounds
        self.bbox = f"{bounds[0]},{bounds[1]},{bounds[2]},{bounds[3]}"
    
    def get_nest_text(self, template, entry):
        def replace(dic):
            for k, v in dic.items():
                if isinstance(v, str):
                    dic[k] = v.format(
                        nest_entry=entries,
                        areaname=self.name,
                        staticmap=""
                    )
                elif isinstance(v, dict):
                    dic[k] = replace(v)
            return dic
        entries = ""
        for nest in self.nests:
            if len(entries) < 1500:
                entries += entry.format(
                    park_name=nest.name,
                    mon_name=nest.mon_id
                )
        return replace(template)

class Park():
    def __init__(self, element, config):
        self._element = element
        self._default_name = config.default_park_name
        self._config = config

        self.polygon = None
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
        if self.id in area_file:
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
            self.lat = center_point.x
            self.lon = center_point.y

        self.get_feature()

    def get_feature(self):
        min_lon, min_lat, max_lon, max_lat = self.polygon.convex_hull.bounds
        properties = {
            "name": self.name,
            "stroke": self._config.json_stroke,
            "stroke-width": self._config.json_stroke_width,
            "stroke-opacity": self._config.json_stroke_opacity,
            "fill": self._config.json_fill,
            "fill-opacity": self._config.json_fill_opacity,
            "area_center_point": geometry.Point(self.lat, self.lon),
            "min_lon": min_lon,
            "min_lat": min_lat,
            "max_lon": max_lon,
            "max_lat": max_lat,
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
                return
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

        self.polygon = final_polygon

        if isinstance(self.polygon, geometry.MultiPolygon):
            polygons = self.polygon.geoms
        else:
            polygons = [self.polygon]

        sql_fence = []
        sql_fences = []
        for polygon in polygons:
            for lon, lat in polygon.exterior.coords:
                sql_fence.append(f"{lat} {lon}")
            sql_fences.append("(" + ",".join(sql_fence) + ")")
        self.sql_fence = ",".join(sql_fences)

        return new_ways