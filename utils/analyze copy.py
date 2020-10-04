import json
import csv
import time
import timeit

from rich.progress import Progress
from shapely import geometry
from shapely.ops import polylabel
from geojson import Feature
from collections import defaultdict

from utils.logging import log
from utils.overpass import get_osm_data
from utils.area import WayPark, RelPark

OSM_DATE = "2019-02-24T00:00:00Z"

def analyze_nests(config, area, nest_mons, queries):

    # Getting OSM/overpass data
    
    osm_file_name = f"osm_data/{area.name} {OSM_DATE.replace(':', '')}.json"
    try:
        with open(osm_file_name, mode="r", encoding="utf-8") as osm_file:
            nest_json = json.load(osm_file)
    except (IOError, OSError):
        log.info("Getting OSM data. This will take ages if this is your first run.")
        osm_time_start = timeit.default_timer()
        nest_json = get_osm_data(area.bbox, OSM_DATE)
        osm_time_stop = timeit.default_timer()
        if not nest_json["elements"]:
            log.error("Did not get any data from overpass.")
            if "remark" in nest_json:
                log.error(nest_json["remark"])
            return
        with open(osm_file_name, mode='w', encoding="utf-8") as osm_file:
            osm_file.write(json.dumps(nest_json, indent=4))
        log.success(f"Done. Got all OSM data in {round(osm_time_stop - osm_time_start, 1)} seconds and saved it.")

    # Getting area data

    area_file_name = f"area_data/{area.name}.csv"
    area_file_data = {}
    try:
        with open(area_file_name, mode="r", encoding="utf-8") as area_file:
            log.info("Found area data file. Reading and using data from it now")
            dict_reader = csv.DictReader(
                area_file,
                quotechar='"',
                quoting=csv.QUOTE_MINIMAL,
            )
            for line in dict_reader:
                area_file_data[line["osm_id"]] = {
                    "name": line["name"],
                    "center_lat": line["center_lat"],
                    "center_lon": line["center_lon"],
                }

    except FileNotFoundError:
        pass

    log.info(f"Got all relevant information. Searching for nests in {area.name} now")

    nodes = dict()
    ways = dict()
    relations = dict()
    for element in nest_json['elements']:
        if not "type" in element:
            continue
        if element["type"] == "node":
            nodes[element["id"]] = {
                "lat": element["lat"],
                "lon": element["lon"]
            }
        elif element["type"] == "way":
            if "nodes" not in element and not element["nodes"]:
                continue
            ways[element["id"]] = element
        elif element["type"] == "relation":
            if "members" not in element and not element["members"]:
                continue
            relations[element["id"]] = element

    # Check Relations

    def _convert_way(way):
        area_points = list()
        for point in way["nodes"]:
            point_coords = nodes[point]
            area_points.append([point_coords['lon'], point_coords['lat']])
        if len(area_points) < 3:
            return
        return geometry.Polygon(area_points)

    areas = dict()
    areas_basic = dict()

    start = timeit.default_timer()
    
    with Progress() as progress:
        check_rels_task = progress.add_task("Checking Relations", total=len(relations))

        for _id, relation in relations.items():
            relation_name = config.default_park_name
            if str(_id) in area_file_data:
                relation_name = area_file_data[str(_id)]["name"]
            elif "tags" in relation and "name" in relation["tags"]:
                relation_name = relation["tags"]["name"]
            elif "tags" in relation and "official_name" in relation["tags"]:
                relation_name = relation["tags"]["official_name"]

            inner_members = list()
            outer_members = list()
            for member in relation["members"]:
                role = member["role"]
                if member["type"] == "node":
                    # this means, this is just a single poi inside the relation
                    continue
                way = ways.get(member["ref"], None)
                if way is None:
                    continue
                way_poly = _convert_way(way)
                if way_poly is None:
                    continue
                if role == "inner":
                    inner_members.append(way_poly)
                else:  #role == "outer" or no inner/outer infos are given
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

            area_shapeley_poly = final_polygon.convex_hull

            if _id in area_file_data:
                center_lat = float(area_file_data[str(_id)]["center_lat"])
                center_lon = float(area_file_data[str(_id)]["center_lon"])
                area_center_point = geometry.Point(center_lat, center_lon)
            elif final_polygon.is_valid:
                if isinstance(final_polygon, geometry.MultiPolygon):
                    final_polygon = list(final_polygon)[0]
                area_center_point = polylabel(final_polygon, tolerance=1e-6)
            else:
                continue

            min_lon, min_lat, max_lon, max_lat = area_shapeley_poly.bounds

            area_poly_props = {
                "name": relation_name,
                "stroke": config.json_stroke,
                "stroke-width": config.json_stroke_width,
                "stroke-opacity": config.json_stroke_opacity,
                "fill": config.json_fill,
                "fill-opacity": config.json_fill_opacity,
                "area_center_point": area_center_point,
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            }
            feat = Feature(
                geometry=final_polygon,
                id=_id,
                properties=area_poly_props)
            areas[_id] = feat

            progress.update(check_rels_task, advance=1)

        # Check Ways
        check_ways_task = progress.add_task("Checking Ways", total=len(ways))
        failed_nests = defaultdict(int)
        failed_nests["Total Nests found"] = 0
        for _id, way in ways.items():
            way_name = config.default_park_name
            if str(_id) in area_file_data:
                way_name = area_file_data[str(_id)]["name"]
            elif "tags" in way and "name" in way["tags"]:
                way_name = way["tags"]["name"]
            elif "tags" in way and "official_name" in way["tags"]:
                way_name = way["tags"]["official_name"]

            way_points = list()
            for point in way['nodes']:
                point_coords = nodes[point]
                way_points.append([point_coords['lon'], point_coords['lat']])
            if len(way_points) < 3:
                continue
            way_poly = geometry.Polygon(way_points)
            way_shapeley_poly = way_poly.convex_hull
            if not way_shapeley_poly.bounds:
                continue

            if str(_id) in area_file_data:
                center_lat = float(area_file_data[str(_id)]["center_lat"])
                center_lon = float(area_file_data[str(_id)]["center_lon"])
                way_center_point = geometry.Point(center_lat, center_lon)
            elif way_poly.is_valid:
                way_center_point = polylabel(way_poly, tolerance=1e-6)
            else:
                continue
            min_lon, min_lat, max_lon, max_lat = way_shapeley_poly.bounds
            way_poly_props = {
                "name": way_name,
                "stroke": config.json_stroke,
                "stroke-width": config.json_stroke_width,
                "stroke-opacity": config.json_stroke_opacity,
                "fill": config.json_fill,
                "fill-opacity": config.json_fill_opacity,
                "area_center_point": way_center_point,
                "min_lon": min_lon,
                "min_lat": min_lat,
                "max_lon": max_lon,
                "max_lat": max_lat,
            }
            feat = Feature(
                geometry=way_poly,
                id=_id,
                properties=way_poly_props)
            areas[_id] = feat

            progress.update(check_ways_task, advance=1)

        # NOW CHECK ALL AREAS ONE AFTER ANOTHER
        check_nest_task = progress.add_task("Nests found: 0", total=len(areas))
        nest_areas = []
        for _id, area_ in areas.items():
            progress.update(check_nest_task, advance=1, description=f"Nests found: {failed_nests['Total Nests found']}")

            area_points = area_["geometry"]
            area_prop = area_["properties"]

            area_center_point = area_prop["area_center_point"]
            sql_fence = []

            for lon, lat in area_points["coordinates"][0]:
                sql_fence.append(f"{lat} {lon}")

            area_pokestops = dict()
            pokestop_in = None
            if config.scanner == "rdm":
                # Get all Pokestops with id, lat and lon
                for pkstp in queries.stops(area.sql_fence):
                    pkst_point = geometry.Point(pkstp[2], pkstp[1])
                    if pkst_point.within(geometry.shape(area_points)):
                        area_pokestops[pkstp[0]] = pkst_point
                pokestop_in = "'{}'".format("','".join(str(nr) for nr in area_pokestops))

            area_spawnpoints = dict()
            for spwn in queries.spawns(",".join(sql_fence)):
                spwn_point = geometry.Point(spwn[1], spwn[2])
                area_spawnpoints[spwn[0]] = spwn_point

            if not area_pokestops and not area_spawnpoints:
                failed_nests["No Stops and no Spawnpoints"] += 1
                continue
            if (len(area_pokestops) < 1) and (len(area_spawnpoints) < area.settings['min_spawnpoints']):
                failed_nests["Not enough Spawnpoints"] += 1
                continue
            spawnpoint_in = "'{}'".format("','".join(str(nr) for nr in area_spawnpoints))
            if spawnpoint_in == "''": spawnpoint_in = "NULL" # This will handle the SQL warning since a blank string shouldn't be used for a number

            # Use data since last change:
            reset_time = int(time.time()) - (config.hours_since_change*3600)
            # RDM uses pokestop_ids, MAD not
            """if config.pokestop_pokemon:
                _city_progress(idx, areas_len, "({}/{}) {}".format(
                    idx,
                    areas_len,
                    "Get all Pokes from stops and spawnpoints within nest area"))
            else:
                _city_progress(idx, areas_len, "({}/{}) {}".format(
                    idx,
                    areas_len,
                    "Get all Pokes from spawnpoints within nest area"))"""

            poke_data = queries.mons(spawnpoint_in, str(tuple(nest_mons)), str(reset_time), pokestop_in)
            poke_id = 0
            poke_count = 0
            if poke_data:
                poke_id, poke_count = map(int, poke_data)

            # (Area_poke/timespan)*(24/scan_hours)
            poke_avg = round(
                (poke_count / float(config.hours_since_change)) * (
                    24.00 / float(area.settings['scan_hours_per_day'])), 2)

            if poke_count < area.settings['min_pokemon']:
                failed_nests["No enough Pokemon"] += 1
                continue
            if poke_avg < area.settings['min_average']:
                failed_nests["Average spawnrate too low"] += 1
                continue

            current_time = int(time.time())

            # Insert Nest data to db
            insert_args = {
                "nest_id": str(area_['id']),
                "name": area_["properties"]["name"],
                "lat": float(area_center_point.x),
                "lon": float(area_center_point.y),
                "pokemon_id": int(poke_id),
                "type": 0,
                "pokemon_count": float(poke_count),
                "pokemon_avg": float(poke_avg),
                "current_time": current_time
            }
            area_file_data[str(area_['id'])] = {
                "name": area_["properties"]["name"],
                "center_lat": float(area_center_point.x),
                "center_lon": float(area_center_point.y),
            }
            failed_nests["Total Nests found"] += 1
            nest_areas.append(area_)

            queries.nest_insert(insert_args)
            areas_basic[str(area_['id'])] = insert_args
    stop = timeit.default_timer()
    log.success(f"Done finding nests in {area.name} ({round(stop - start, 1)} seconds)")
    for k, v in failed_nests.items():
        log.info(f" - {k}: {v}")

    with open(area_file_name, mode="w+") as area_file:
        fieldnames = [u"name", u"center_lat", u"center_lon", u"osm_id"]
        dict_writer = csv.DictWriter(
            area_file,
            fieldnames=fieldnames,
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
        )
        dict_writer.writeheader()
        for a_id, a_data in area_file_data.items():
            dict_writer.writerow({
                "osm_id": a_id,
                "name": u"" + a_data["name"],
                "center_lat": a_data["center_lat"],
                "center_lon": a_data["center_lon"],
            })
        log.info("Saved area data")

    return nest_areas