"""
Script to analyze Nests in combination with db and OSM data.
It inserts the Nests inside the db so PMSF can show them.

Original Creator racinel200 and abakedapplepie
Refactored by M4d40
"""


from collections import defaultdict, OrderedDict
import datetime, argparse, csv, io, json, sys, time, requests, os

from shapely import geometry
from pymysql import connect
from rich.progress import Progress
from geojson import (
    Feature,
    FeatureCollection,
    dumps
)
from serebii import SerebiiPokemonGo
from utils.config import Config
from utils.overpass import get_osm_data
from utils.area import Area
from utils.queries import Queries
#from utils.logging import log

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote
try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

DEFAULT_CONFIG = "default.ini"
POKE_NAMES_FILE = "poke_names.json"

FILENAME = "osm_data/OSM_DATA_{area}_{date}.json"
PARKNAME_FILE = "area_data/{area}.csv"
OSM_DATE = "2019-02-24T00:00:00Z"

def analyze_nest_data(config, area):
    print(f"Getting nests for area {area.name}")
    with open("config/settings.json", "r") as f:
        settingsfile = json.load(f)
    settings = settingsfile["defaults"]
    if area.name in settingsfile.keys():
        for k, v in settingsfile[area.name]:
            settings[k] = v

    start_time = time.time()
    osm_file_name = FILENAME.format(
        area=area.name,
        date=OSM_DATE)
    try:
        with open(osm_file_name, mode='r', encoding="utf-8") as osm_file:
            nest_json = json.load(osm_file)
    except (IOError, OSError):
        print("No OSM Data file found, will get the data now. Please be patient.")
        nest_json = get_osm_data(area.bbox, OSM_DATE)
        if not nest_json["elements"]:
            print("Did not get any Data from the API:")
            if "remark" in nest_json:
                print(nest_json["remark"])
            return
        with open(osm_file_name, mode='w', encoding="utf-8") as osm_file:
            osm_file.write(json.dumps(nest_json, indent=4))
        print("Saved OSM File.")

    # global nest_json
    if not nest_json:
        print("Error getting osm data from file")
        print(nest_json)
        return

    # This is where will will grab a name file for today
    """name_date=str(datetime.date.today())+'T00:00:00Z'

    osm_4name_file_name = FILENAME.format(
        area=area.name+'_NAMES',
        date=name_date)
    try:
        with io.open(osm_4name_file_name, mode='r', encoding="utf-8") as osm_4name_file:
            print("OSM Name Data file found for the {}, we will use this! :D".format(name_date))
            name_json = json.loads(osm_4name_file.read())
    except (IOError, OSError):
        print("No OSM Name Data file found for the {}, will get the data now.\n".format(name_date))
        nest_json = get_osm_data(area.bbox, name_dates)

        if not name_json["elements"]:
            print("\nDid not get any Data from the API:")
            if "remark" in name_json:
                print(name_json["remark"])
            return

        print("Removing old Name Data files")
        for file in os.listdir("osm_data/"):
            if file.startswith("OSM_DATA_"+config['area_name']+"_NAMES_"):
                os.remove(os.path.join("osm_data/",file))

        with io.open(osm_4name_file_name, mode='w', encoding="utf-8") as osm_4name_file:
            osm_4name_file.write(response.text)
            print("OSM Name Data received and is saved in OSM Data file")"""

    if not name_json:
        print("Error getting osm name data from file")
        print(name_json)
        return

    # Check if any of the unnamed parks have names in the new file
    found_new_name = False
    for element in nest_json['elements']:
        if element["type"] != "node":
            if "tags" in element:
                tags = element["tags"]
                if "name" not in tags and "official_name" not in tags:
                    for element_name in name_json['elements']:
                        if element_name["type"] != "node" and element["id"] == element_name["id"] and "tags" in element_name and\
                        ("name" in element_name["tags"] or "official_name" in element_name["tags"]):
                            if "name" in element_name["tags"]:
                                print("We found a name in the OSM Name data: {}".format(element_name["tags"]["name"]))
                                found_new_name = True
                                tags["name"] = element_name["tags"]["name"]
                            elif "official_name" in element_name["tags"]:
                                print("We found a name in the OSM Name data: {}".format(element_name["tags"]["official_name"]))
                                found_new_name = True
                                tags["official_name"] = element_name["tags"]["official_name"]

    # If there are new names, write the updated JSON to the data file
    if found_new_name:
        with io.open(osm_file_name, mode='w', encoding="utf-8") as osm_file:
            osm_file.write(json.dumps(nest_json, indent=4))
            print("OSM Data file updated with new names")
    else:
        print("No new names found")

    print("Getting OSM Data...Complete (took {:.2f} minutes)".format((time.time() - start_time)/60))

    # Read the Area Data File
    area_file_name = PARKNAME_FILE.format(area=area.name)
    area_file_data = dict()
    try:
        with open(area_file_name, mode='r', encoding="utf-8") as area_file:
            print("Area Data file found, we will use this! :D")
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

        # If there was a new name, updated the CSV file too
        if found_new_name:
            print("Adding new names to the CSV file")
            for a_id, a_data in area_file_data.items():
                if a_data["name"] == config.default_park_name:
                    for element_name in name_json['elements']:
                        if element_name["type"] != "node" and int(a_id) == element_name["id"] and ("name" in element_name["tags"] or "official_name" in element_name["tags"]):
                            if "name" in element_name["tags"]:
                                print("Update the name for ID: {} to the name: {}".format(a_id, element_name["tags"]["name"]))
                                a_data["name"] = element_name["tags"]["name"]
                            if "official_name" in element_name["tags"]:
                                print("Update the name for ID: {} to the name: {}".format(a_id, element_name["tags"]["official_name"]))
                                a_data["name"] = element_name["tags"]["official_name"]

            with open(area_file_name, mode='w', encoding="utf-8") as area_file:
                print("Rewriting area data file...")
                fieldnames = [u"name", u"center_lat", u"center_lon", u"osm_id"]
                dict_writer = csv.DictWriter(
                    area_file,
                    fieldnames=fieldnames,
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                dict_writer.writeheader()
                # This ONLY WORKS on Python3 str, unicode with write
                for a_id, a_data in area_file_data.items():
                    dict_writer.writerow({
                        "osm_id": a_id,
                        "name": u"" + a_data["name"],
                        "center_lat": a_data["center_lat"],
                        "center_lon": a_data["center_lon"],
                    })
                print("Area names updated successfully")

    except FileNotFoundError:
        print("No Area Data file found, we will create it at the end\n")

    # Get Event Data
    print("Checking for active events")
    print("Event Source:", config.event_source)
    event_pokes = set()
    if config.event_source == "serebii":
        serebii = SerebiiPokemonGo()
        active_events = serebii.get_active_events()
        event_pokes = set()
        if active_events:
            print("Active Event(s) found:")
            print(active_events)
            for event in active_events:
                event_pokes.update(event.pokemon)

    elif config.event_source == "ccev":
        r = requests.get("https://raw.githubusercontent.com/ccev/pogoinfo/info/events/active.json")
        pogoinfo_events = r.json()
        if isinstance(pogoinfo_events, dict):
            pogoinfo_events = [pogoinfo_events]
        for event in pogoinfo_events:
            if datetime.datetime.strptime(
                    event["end"], "%Y-%m-%d %H:%M") > datetime.datetime.now():
                print("Active Event found:")
                print(event["name"])
                for mon in event["details"]["spawns"]:
                    try:
                        event_pokes.update(int(mon.split("_")[0]))
                    except:
                        pass
    else:
        print("Unkown event source, use 'serebii' or 'ccev'")
    if not event_pokes:
        print("Currently there seems to be no Event Pokemon")

    nest_mons = requests.get("https://pogoapi.net/api/v1/nesting_pokemon.json").json().keys()

    print("##"*20)

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
    print("Initialize/Start DB Session")
    queries = Queries(config)
    print("Connection clear")
    queries.nest_delete

    print("Start Analyzing Nests")

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
    relations_len = len(relations)
    print("Starting to analyze Nest - Check Relations")
    for (idx, (_id, relation)) in enumerate(relations.items(), start=1):
        relation_name = config.default_park_name
        if str(_id) in area_file_data:
            print("ID Found in Area File, will use data from area file")
            relation_name = area_file_data[str(_id)]["name"]
        elif "tags" in relation and "name" in relation["tags"]:
            relation_name = relation["tags"]["name"]
        elif "tags" in relation and "official_name" in relation["tags"]:
            relation_name = relation["tags"]["official_name"]
        _city_progress(idx, relations_len, "({}/{}) {}".format(
            idx,
            relations_len,
            "Starting to analyze Nest - Check Relations"))
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
        else:
            area_center_point = area_shapeley_poly.centroid
        if not area_shapeley_poly.bounds:
            continue

        min_lon, min_lat, max_lon, max_lat = area_shapeley_poly.bounds

        area_poly_props = {
            "name": relation_name,
            "stroke": config["json-stroke"],
            "stroke-width": config['json-stroke-width'],
            "stroke-opacity": config['json-stroke-opacity'],
            "fill": config['json-fill'],
            "fill-opacity": config['json-fill-opacity'],
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

    # Check Ways
    all_areas = list()
    failed_nests = defaultdict(int)
    ways_len = len(ways)
    print("\nStarting to analyze Nest - Check Ways")
    for (idx, (_id, way)) in enumerate(ways.items(), start=1):
        way_name = config.default_park_name
        if str(_id) in area_file_data:
            way_name = area_file_data[str(_id)]["name"]
        elif "tags" in way and "name" in way["tags"]:
            way_name = way["tags"]["name"]
        elif "tags" in way and "official_name" in way["tags"]:
            way_name = way["tags"]["official_name"]
        _city_progress(idx, ways_len, "({}/{}) {}".format(
            idx,
            ways_len,
            "Starting to analyze Nest - Check Ways"))
        way_points = list()
        for point in way['nodes']:
            point_coords = nodes[point]
            way_points.append([point_coords['lon'], point_coords['lat']])
        if len(way_points) < 3:
            continue
        way_poly = geometry.Polygon(way_points)
        way_shapeley_poly = way_poly.convex_hull
        if str(_id) in area_file_data:
            center_lat = float(area_file_data[str(_id)]["center_lat"])
            center_lon = float(area_file_data[str(_id)]["center_lon"])
            way_center_point = geometry.Point(center_lat, center_lon)
        else:
            way_center_point = way_shapeley_poly.centroid
        min_lon, min_lat, max_lon, max_lat = way_shapeley_poly.bounds
        way_poly_props = {
            "name": way_name,
            "stroke": config["json-stroke"],
            "stroke-width": config['json-stroke-width'],
            "stroke-opacity": config['json-stroke-opacity'],
            "fill": config['json-fill'],
            "fill-opacity": config['json-fill-opacity'],
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

    # NOW CHECK ALL AREAS ONE AFTER ANOTHER
    areas_len = len(areas)
    print("\nStarting to analyze Nest - Filtering")
    for (idx, (_id, area)) in enumerate(areas.items(), start=1):
        area_points = area["geometry"]
        area_prop = area["properties"]

        area_center_point = area_prop["area_center_point"]
        min_lon = area_prop["min_lon"]
        min_lat = area_prop["min_lat"]
        max_lon = area_prop["max_lon"]
        max_lat = area_prop["max_lat"]

        area_pokestops = dict()
        pokestop_in = None
        if config.scanner == "rdm":
            # Get all Pokestops with id, lat and lon
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokestops within min/max lat/lon"))

            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Got all wanted Pokestops - now filter them"))
            for pkstp in queries.stops(area.sql_fence):
                pkst_point = geometry.Point(pkstp[2], pkstp[1])
                if pkst_point.within(geometry.shape(area_points)):
                    area_pokestops[pkstp[0]] = pkst_point
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Filtering of all Pokestops complete"))
            pokestop_in = "'{}'".format("','".join(str(nr) for nr in area_pokestops))

        area_spawnpoints = dict()
        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Get all Spawnpoints within min/max lat/lon"))
        # Get all Spawnpoints with id, lat and lon
        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Got all wanted Spawnpoints - now filter them"))
        for spwn in queries.spawns(area.sql_fence):
            spwn_point = geometry.Point(spwn[2], spwn[1])
            if spwn_point.within(geometry.shape(area_points)):
                area_spawnpoints[spwn[0]] = spwn_point
        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Filtering of all Spawnpoints complete"))

        if not area_pokestops and not area_spawnpoints:
            failed_nests["Park has no Stops and no Spawnpoints, ignore it"] += 1
            continue
        if (len(area_pokestops) < 1) and (len(area_spawnpoints) < settings['min_spawnpoints']):
            failed_nests["Park has not enough Spawnpoints, ignore it"] += 1
            continue
        spawnpoint_in = "'{}'".format("','".join(str(nr) for nr in area_spawnpoints))
        if spawnpoint_in == "''": spawnpoint_in = "NULL" # This will handle the SQL warning since a blank string shouldn't be used for a number

        # Use data since last change:
        reset_time = int(time.time()) - (config.hours_since_change*3600)
        # RDM uses pokestop_ids, MAD not
        if config.pokestop_pokemon:
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokes from stops and spawnpoints within nest area"))
        else:
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokes from spawnpoints within nest area"))

        poke_data = queries.mons(spawnpoint_in, str(tuple(nest_mons)), str(reset_time), pokestop_in)
        if poke_data:
            poke_id, poke_count = map(int, poke_data)

        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Got all Pokes from Nest area"))

        # (Area_poke/timespan)*(24/scan_hours)
        poke_avg = round(
            (poke_count / float(config.hours_since_change)) * (
                24.00 / float(settings['scan_hours_per_day'])), 2)

        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Filter and insert Nests"))
        if poke_count < settings['min_pokemon']:
            failed_nests["Not enough Pokes in this Area to specify a real Nest"] += 1
            continue
        if poke_avg < settings['min_average']:
            failed_nests["Average lower than the min average in config"] += 1
            continue

        current_time = int(time.time())

        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Found Probable Nest - insert it now in db"))
        # Insert Nest data to db
        insert_query = NEST_INSERT_QUERY.format(
            db_name=config['db_w_name'],
            db_nests=config['db_nest'])

        insert_args = {
            "nest_id": str(area['id']),
            "name": area["properties"]["name"],
            "lat": float(area_center_point.x),
            "lon": float(area_center_point.y),
            "pokemon_id": int(poke_id),
            "type": 0,
            "pokemon_count": float(poke_count),
            "pokemon_avg": float(poke_avg),
            "current_time": current_time
        }
        area_file_data[str(area['id'])] = {
            "name": area["properties"]["name"],
            "center_lat": float(area_center_point.x),
            "center_lon": float(area_center_point.y),
        }

        mycursor_w.execute(insert_query, insert_args)
        all_areas.append(area)
        insert_args["pokemon_name"] = poke_names[str(poke_id)][config["dc-language"]]
        insert_args["pokemon_type"] = poke_names[str(poke_id)]["type"]
        insert_args["pokemon_shiny"] = poke_names[str(poke_id)]["shiny"]
        areas_basic[str(area['id'])] = insert_args

    queries.close()

    print("\nNest analyzing took {:.2f} minutes".format((time.time() - start_time)/60))
    if all_areas:
        print("Total Nests Added: {}".format(len(all_areas)))
    else:
        print("No Nests Added")
    if failed_nests:
        print("############ Reasons why nests were not added ############")
        for (key, value) in failed_nests.items():
            print("{}: {}".format(key, value))
        print("##########################################################")
    else:
        print("No false positive Parks")

    if config['geojson_extend']:
        with open(config['save_path'], 'r') as old_file_:
            old_geojson = json.load(old_file_)
            all_areas += old_geojson['features']
            print('Old areas added to the new ones')
    with open(config['save_path'], 'w') as file_:
        print('Writing geojson file')
        file_.write(dumps(FeatureCollection(all_areas), indent=4))
        print("GeoJSON file saved successfully")

    with io.open(area_file_name, mode='w', encoding="utf-8") as area_file:
        print("Writing area data file...")
        fieldnames = [u"name", u"center_lat", u"center_lon", u"osm_id"]
        dict_writer = csv.DictWriter(
            area_file,
            fieldnames=fieldnames,
            quotechar='"',
            quoting=csv.QUOTE_MINIMAL,
        )
        dict_writer.writeheader()
        # This ONLY WORKS on Python3 str, unicode with write
        for a_id, a_data in area_file_data.items():
            dict_writer.writerow({
                "osm_id": a_id,
                "name": u"" + a_data["name"],
                "center_lat": a_data["center_lat"],
                "center_lon": a_data["center_lon"],
            })
        print("Area data file saved successfully")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="configs/config.ini", help="Config file to use")
    parser.add_argument("-h", "--hours", default=None, help="Hours since last migration")
    args = parser.parse_args()
    config_path = args.config
    config = Config(config_path)
    if not args.hours is None:
        config.hours_since_change = args.hours

    with open("config/areas.json", "r") as f:
        areas = json.load(f)
    with open("config/settings.json", "r") as f:
        config.settings = json.load(f)

    for area in areas:
        area = Area(area)
        analyze_nest_data(config, area)
