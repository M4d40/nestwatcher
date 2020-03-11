"""
Script to analyze Nests in combination with db and OSM data.
It inserts the Nests inside the db so PMSF can show them.

Original Creator racinel200 and abakedapplepie
Refactored by M4d40
"""


from collections import defaultdict, OrderedDict
from datetime import datetime

import argparse
import csv
import io
import json
import sys
import time

import requests

from shapely import geometry
from pymysql import connect
from geojson import (
    Feature,
    FeatureCollection,
    dumps
)
from serebii import SerebiiPokemonGo

# Python2 and Python3 compatibility
try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser
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

DISCORD_MAX_MSG = 2000 - 100  # -100 to be sure under the limit
DISCORD_RATE_LIMIT = 1  # in second

FILENAME = "osm_data/OSM_DATA_{area}_{date}.json"
PARKNAME_FILE = "area_data/{area}.csv"

### Overpass api data
OSM_API = "https://overpass-api.de/api/interpreter"
OSM_TAGS = """
way["landuse"="farmland"];
way["landuse"="farmyard"];
way["landuse"="grass"];
way["landuse"="greenfield"];
way["landuse"="meadow"];
way["landuse"="orchard"];
way["landuse"="recreation_ground"];
way["landuse"="vineyard"];
way["leisure"="garden"];
way["leisure"="golf_course"];
way["leisure"="park"];
way["leisure"="pitch"];
way["leisure"="playground"];
way["leisure"="recreation_ground"];
way["natural"="grassland"];
way["natural"="heath"];
way["natural"="scrub"];
"""

OSM_TAGS_RELATIONS = """
rel["landuse"="farmland"];
rel["landuse"="farmyard"];
rel["landuse"="grass"];
rel["landuse"="greenfield"];
rel["landuse"="meadow"];
rel["landuse"="orchard"];
rel["landuse"="recreation_ground"];
rel["landuse"="vineyard"];
rel["leisure"="garden"];
rel["leisure"="golf_course"];
rel["leisure"="park"];
rel["leisure"="pitch"];
rel["leisure"="playground"];
rel["leisure"="park"];
rel["leisure"="recreation_ground"];
rel["natural"="grassland"];
rel["natural"="heath"];
rel["natural"="moor"];
rel["natural"="plateau"];
rel["natural"="scrub"];
"""

### Nesting Species
# Updated 2019.01.30
NEST_G1 = [
    1, 4, 7, 25, 35, 37, 43,
    54, 58, 60, 63, 66, 72,
    77, 81, 84, 86, 90, 92, 95,
    100, 102, 104, 111, 116, 123, 124,
    125, 126, 127, 129, 133, 138, 140
]
NEST_G2 = [
    152, 155, 158, 170, 185, 190, 193,
    200, 202, 203, 206, 209, 211, 213,
    215, 216, 220, 226, 227, 231, 234
]
NEST_G3 = [
    252, 255, 258, 261, 273, 278, 283, 285, 296, 299,
    300, 302, 307, 309, 311, 312, 318, 320, 322, 325,
    333, 341, 343, 345, 347, 353, 355, 370
]
NEST_G4 = [
    387, 390, 393, 399, 401, 427, 434, 449, 453
]
NEST_G5 = [
    495, 498, 501, 504, 506, 509, 522, 590
]
NEST_SPECIES_LIST = (
    NEST_G1 + NEST_G2 + NEST_G3 + NEST_G4 + NEST_G5)

# SQL Queries #
###############

POKESTOP_SELECT_QUERY = """SELECT id, lat, lon FROM {db_name}.{db_pokestop}
WHERE (
    lat >= {min_lat} AND lat <= {max_lat}
  AND
    lon >= {min_lon} AND lon <= {max_lon}
)
"""
SPAWNPOINT_SELECT_QUERY = """SELECT {sp_id}, {lat}, {lon} FROM {db_name}.{db_spawnpoint}
WHERE (
    {lat} >= {min_lat} AND {lat} <= {max_lat}
  AND
    {lon} >= {min_lon} AND {lon} <= {max_lon}
)
"""
NEST_SELECT_QUERY = """SELECT pokemon_id, COUNT(pokemon_id) AS count
FROM {db_name}.{db_pokemon_table}
WHERE (
    (
        {spawn_id} IN ({spawnpoint_in})
    )
    AND
    pokemon_id IN {nest_mons}
    AND
    UNIX_TIMESTAMP({pokemon_timestamp}) >= {reset_time})
GROUP BY pokemon_id
ORDER BY count desc
LIMIT 1"""
NEST_SELECT_QUERY_STOP = """SELECT pokemon_id, COUNT(pokemon_id) AS count
FROM {db_name}.{db_pokemon_table}
WHERE (
    (
        pokestop_id IN ({pokestop_in})
        OR
        {spawn_id} IN ({spawnpoint_in})
    )
    AND
    pokemon_id IN {nest_mons}
    AND
    UNIX_TIMESTAMP({pokemon_timestamp}) >= {reset_time})
GROUP BY pokemon_id
ORDER BY count desc
LIMIT 1"""
NEST_DELETE_QUERY = "DELETE FROM {db_name}.{db_nests}"
NEST_INSERT_QUERY = """INSERT INTO {db_name}.{db_nests} (
    nest_id, name, lon, lat, pokemon_id, type, pokemon_count, pokemon_avg, updated)
VALUES(
    %(nest_id)s, %(name)s, %(lat)s,%(lon)s,
    %(pokemon_id)s, %(type)s, %(pokemon_count)s, %(pokemon_avg)s, %(current_time)s)
ON DUPLICATE KEY UPDATE
    pokemon_id = %(pokemon_id)s,
    name = %(name)s,
    type = %(type)s,
    pokemon_count = %(pokemon_count)s,
    pokemon_avg = %(pokemon_avg)s,
    updated = %(current_time)s
"""


def progress(count, total, status=''):
    """ progress bar: https://gist.github.com/vladignatyev/06860ec2040cb497f0f3"""
    bar_len = 60
    filled_len = int(round(bar_len * count / float(total)))

    percents = round(100.0 * count / float(total), 1)
    pbar = '=' * filled_len + '-' * (bar_len - filled_len)
    sys.stdout.write('[%s] %s%s ...%s\r' % (pbar, percents, '%', status))
    sys.stdout.flush()

def create_config(config_path):
    """ Parse config. """
    config = dict()
    config_raw = ConfigParser()
    config_raw.read(DEFAULT_CONFIG)
    config_raw.read(config_path)
    config['timespan'] = config_raw.getint(
        'Nest Config',
        'TIMESPAN_SINCE_CHANGE')
    config['min_pokemon'] = config_raw.getint(
        'Nest Config',
        'MIN_POKEMON_NEST_COUNT')
    config['min_avg_pokemon'] = config_raw.getfloat(
        'Nest Config',
        'MIN_AVERAGE_POKEMON_NEST_COUNT')
    config['min_spawn'] = config_raw.getint(
        'Nest Config',
        'MIN_SPAWNPOINT_NEST_COUNT')
    config['delete_old'] = config_raw.getboolean(
        'Nest Config',
        'DELETE_OLD_NESTS')
    config['event_automation'] = config_raw.getboolean(
        'Nest Config',
        'EVENT_AUTOMATION')
    config['event_poke'] = json.loads(config_raw.get(
        'Nest Config',
        'MANUAL_EVENT_POKEMON'))
    config['pokestop_pokemon'] = config_raw.getboolean(
        'Nest Config',
        'POKESTOP_POKEMON')
    config['analyze_multipolygons'] = config_raw.getboolean(
        'Nest Config',
        'ANALYZE_MULTIPOLYGONS')
    config['area_name'] = config_raw.get(
        'Area',
        'NAME')
    config['scan_hours'] = config_raw.getfloat(
        'Area',
        'SCAN_HOURS_PER_DAY')
    config['p1_lat'] = config_raw.getfloat(
        'Area',
        'POINT1_LAT')
    config['p1_lon'] = config_raw.getfloat(
        'Area',
        'POINT1_LON')
    config['p2_lat'] = config_raw.getfloat(
        'Area',
        'POINT2_LAT')
    config['p2_lon'] = config_raw.getfloat(
        'Area',
        'POINT2_LON')
    config['db_r_host'] = config_raw.get(
        'DB Read',
        'HOST')
    config['db_r_name'] = config_raw.get(
        'DB Read',
        'NAME')
    config['db_r_user'] = config_raw.get(
        'DB Read',
        'USER')
    config['db_r_pass'] = config_raw.get(
        'DB Read',
        'PASSWORD')
    config['db_r_port'] = config_raw.getint(
        'DB Read',
        'PORT')
    config['db_r_charset'] = config_raw.get(
        'DB Read',
        'CHARSET')
    config['db_pokemon'] = config_raw.get(
        'DB Read',
        'TABLE_POKEMON')
    config['db_pokemon_spawnid'] = config_raw.get(
        'DB Read',
        'TABLE_POKEMON_SPAWNID')
    config['db_pokemon_timestamp'] = config_raw.get(
        'DB Read',
        'TABLE_POKEMON_TIMESTAMP')
    config['db_pokestop'] = config_raw.get(
        'DB Read',
        'TABLE_POKESTOP')
    config['db_spawnpoint'] = config_raw.get(
        'DB Read',
        'TABLE_SPAWNPOINT')
    config['db_spawnpoint_id'] = config_raw.get(
        'DB Read',
        'TABLE_SPAWNPOINT_ID')
    config['db_spawnpoint_lat'] = config_raw.get(
        'DB Read',
        'TABLE_SPAWNPOINT_LAT')
    config['db_spawnpoint_lon'] = config_raw.get(
        'DB Read',
        'TABLE_SPAWNPOINT_LON')
    config['use_unix_timestamp'] = config_raw.getboolean(
        'DB Read',
        'USE_UNIX_TIMESTAMP')
    config['db_w_host'] = config_raw.get(
        'DB Write',
        'HOST')
    config['db_w_name'] = config_raw.get(
        'DB Write',
        'NAME')
    config['db_w_user'] = config_raw.get(
        'DB Write',
        'USER')
    config['db_w_pass'] = config_raw.get(
        'DB Write',
        'PASSWORD')
    config['db_w_port'] = config_raw.getint(
        'DB Write',
        'PORT')
    config['db_w_charset'] = config_raw.get(
        'DB Write',
        'CHARSET')
    config['db_nest'] = config_raw.get(
        'DB Write',
        'TABLE_NESTS')
    config['save_path'] = config_raw.get(
        'Geojson',
        'SAVE_PATH')
    config['geojson_extend'] = config_raw.getboolean(
        'Geojson',
        'GEOJSON_EXTEND')
    config['default_park_name'] = config_raw.get(
        'Geojson',
        'DEFAULT_PARK_NAME')
    config['json-stroke'] = config_raw.get(
        'Geojson',
        'STROKE')
    config['json-stroke-width'] = config_raw.getfloat(
        'Geojson',
        'STROKE-WIDTH')
    config['json-stroke-opacity'] = config_raw.getfloat(
        'Geojson',
        'STROKE-OPACITY')
    config['json-fill'] = config_raw.get(
        'Geojson',
        'FILL')
    config['json-fill-opacity'] = config_raw.getfloat(
        'Geojson',
        'FILL-OPACITY')
    config['dc-enabled'] = config_raw.getboolean(
        'Discord',
        'ENABLED')
    config['dc-webhook'] = config_raw.get(
        'Discord',
        'WEBHOOK')
    config['dc-username'] = config_raw.get(
        'Discord',
        'USERNAME')
    config['dc-language'] = config_raw.get(
        'Discord',
        'LANGUAGE')
    config['dc-min-spawns-for-post'] = config_raw.getfloat(
        'Discord',
        'MIN_SPAWNS_FOR_POST')
    config['dc-title'] = config_raw.get(
        'Discord',
        'TITLE')
    config['dc-text'] = config_raw.get(
        'Discord',
        'TEXT')
    config['dc-sort-by'] = config_raw.get(
        'Discord',
        'SORT_BY')
    config['dc-sort-reverse'] = config_raw.getboolean(
        'Discord',
        'SORT_REVERSE')
    config['dc-ignore-unnamed'] = config_raw.getboolean(
        'Discord',
        'IGNORE_UNNAMED')
    config['dc-locale-file'] = config_raw.get(
        'Discord',
        'LOCALE_FILE')
    config['dc-map-link'] = config_raw.get(
        'Discord',
        'MAP_LINK')
    config['encoding'] = config_raw.get(
        'Other',
        'ENCODING')
    config['verbose'] = config_raw.getboolean(
        'Other',
        'VERBOSE')
    config['osm_date'] = config_raw.get(
        'Other',
        'OSM_DATE')


    return config


def print_configs(config):
    """Print the used config."""
    print("\nFollowing Configs will be used:")
    print("Area: {}".format(config["area_name"]))
    print("-"*15)
    print("{} hours will be used as timespan".format(config['timespan']))
    print("Minimum amount of pokes to count as Nest: {}".format(config['min_pokemon']))
    if config['event_automation']:
        print("Event Automation is activated, we will grab Event Details from Serebii")
    else:
        print("Manual Event Pokemon:: {}".format(str(config['event_poke'])))
    print("Delete Old Nests from DB: {}".format(str(config['delete_old'])))
    print("File will be saved in: {}".format(str(config['save_path'])))
    print("Analyze Multipolygons: {}".format(str(config['analyze_multipolygons'])))
    if config['verbose']:
        print("-"*15)
        print("\nVerbose Config:")
        print("Point 1: {lat}, {lon}".format(
            lat=config['p1_lat'],
            lon=config['p1_lon']))
        print("Point 2: {lat}, {lon}".format(
            lat=config['p2_lat'],
            lon=config['p2_lon']))
        print("")
        print("DB Read:")
        print("Host: {}".format(config['db_r_host']))
        print("Name: {}".format(config['db_r_name']))
        print("User: {}".format(config['db_r_user']))
        print("Password: {}".format(config['db_r_pass']))
        print("Port: {}".format(config['db_r_port']))
        print("Charset: {}".format(config['db_r_charset']))
        print("")
        print("DB Read:")
        print("Host: {}".format(config['db_w_host']))
        print("Name: {}".format(config['db_w_name']))
        print("User: {}".format(config['db_w_user']))
        print("Password: {}".format(config['db_w_pass']))
        print("Port: {}".format(config['db_w_port']))
        print("Charset: {}".format(config['db_w_charset']))
    print("~"*15)


def osm_uri(p1_lat, p1_lon, p2_lat, p2_lon, osm_date, relations=False):
    """Generate the OSM uri for the OSM data"""
    osm_bbox = "[bbox:{p1_lat},{p1_lon},{p2_lat},{p2_lon}]".format(
        p1_lat=p1_lat,
        p1_lon=p1_lon,
        p2_lat=p2_lat,
        p2_lon=p2_lon
    )
    osm_data = "?data="
    osm_type = "[out:json]"
    date = '[date:"{osm_date}"];'.format(osm_date=osm_date)
    if relations:
        print("\nDO IT BIIIIIGGG WITH RELATIONS !!!!\n")
        #tag_data = (OSM_TAGS + OSM_TAGS_RELATIONS).replace("\n", "")
        tag_data = (OSM_TAGS_RELATIONS).replace("\n", "")
    else:
        print("\n   Keeep ittt siimpleee\n")
        tag_data = OSM_TAGS.replace("\n", "")
    osm_tag_data = "({osm_tags});".format(osm_tags=tag_data)
    osm_end = "out;>;out skel qt;"
    uri = OSM_API + osm_data + quote(osm_type + osm_bbox + date + osm_tag_data + osm_end)
    return uri


def analyze_nest_data(config):
    """ Analyze nest data """

    def _city_progress(count, total, status=""):
        status = "[{}] {}".format(config["area_name"], status)
        progress(count, total, status)
    start_time = time.time()
    osm_file_name = FILENAME.format(
        area=config['area_name'],
        date=config['osm_date'])
    try:
        with io.open(osm_file_name, mode='r', encoding=config["encoding"]) as osm_file:
            print("OSM Data file found, we will use this! :D")
            nest_json = json.loads(osm_file.read())
    except IOError:
        print("No OSM Data file found, will get the data now.\n")
        nest_url = osm_uri(
            config['p1_lat'],
            config['p1_lon'],
            config['p2_lat'],
            config['p2_lon'],
            config['osm_date'],
            relations=config['analyze_multipolygons'],
        )
        print("{} Overpass url:".format(config["area_name"]))
        print(nest_url)
        print("Getting OSM Data...")
        osm_session = requests.Session()

        response = osm_session.get(nest_url)
        response.raise_for_status()
        nest_json = response.json()
        print(nest_json)
        # global nest_json
        if not nest_json["elements"]:
            print("\nDid not get any Data from the API:")
            if "remark" in nest_json:
                print(nest_json["remark"])
            return
        with io.open(osm_file_name, mode='w', encoding=config["encoding"]) as osm_file:
            osm_file.write(response.text)
            print("OSM Data received and is saved in OSM Data file")

    # global nest_json
    if not nest_json:
        print("Error getting osm data from file")
        print(nest_json)
        return

    print("Getting OSM Data...Complete (took {} seconds)".format(time.time()))

    # Read the Area Data File
    area_file_name = PARKNAME_FILE.format(area=config['area_name'])
    area_file_data = dict()
    try:
        with io.open(area_file_name, mode='r', encoding=config["encoding"]) as area_file:
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
    except FileNotFoundError:
        print("No Area Data file found, we will create it at the end\n")

    # Get Event Data
    event_pokes = set(config['event_poke'])
    if config['event_automation']:
        print("Event-Automation active, checking for active events")
        serebii = SerebiiPokemonGo()
        active_events = serebii.get_active_events()
        event_pokes = set()
        if active_events:
            print("Active Events found:")
            print(active_events)
            for event in active_events:
                event_pokes.update(event.pokemon)
        else:
            print("Currently no active Event found, no event pokemon will be used")

    if NEST_SPECIES_LIST:
        nest_mons = set(NEST_SPECIES_LIST) - event_pokes
    else:
        nest_mons = set()
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
    mydb_r = connect(
        host=config['db_r_host'],
        user=config['db_r_user'],
        passwd=config['db_r_pass'],
        database=config['db_r_name'],
        port=config['db_r_port'],
        charset=config['db_r_charset'],
        autocommit=True)
    mydb_w = connect(
        host=config['db_w_host'],
        user=config['db_w_user'],
        passwd=config['db_w_pass'],
        database=config['db_w_name'],
        port=config['db_w_port'],
        charset=config['db_w_charset'],
        autocommit=True)

    mycursor_r = mydb_r.cursor()
    mycursor_w = mydb_w.cursor()
    print("Connection clear")
    # Delete old Nest data
    if config['delete_old']:
        print("Delete Old Nests")
        mycursor_w.execute(
            NEST_DELETE_QUERY.format(
                db_name=config['db_w_name'],
                db_nests=config['db_nest']
            )
        )
        print("Delete Old Nests - Complete")
    print("Start Analyzing Nests")

    # Check Relations

    def _convert_way(way):
        area_points = list()
        for point in way["nodes"]:
            point_coords = nodes[point]
            area_points.append([point_coords['lon'], point_coords['lat']])
        if len(area_points) < 3:
            return None  # I know i don't need, but return alone looks sad ^^
        return geometry.Polygon(area_points)

    with open(POKE_NAMES_FILE) as pk_names_file:
        poke_names = json.load(pk_names_file)
    with open(config['dc-locale-file']) as loc_file:
        locale = json.load(loc_file)
    areas = dict()
    areas_basic = dict()
    relations_len = len(relations)
    for (idx, (_id, relation)) in enumerate(relations.items(), start=1):
        relation_name = config['default_park_name']
        if str(_id) in area_file_data:
            print("ID Found in Area File, will use data from area file")
            relation_name = area_file_data[str(_id)]["name"]
        elif "tags" in relation and "name" in relation["tags"]:
            relation_name = relation["tags"]["name"]
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
            way = ways.pop(member["ref"], None)
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
    for (idx, (_id, way)) in enumerate(ways.items(), start=1):
        way_name = config['default_park_name']
        if str(_id) in area_file_data:
            way_name = area_file_data[str(_id)]["name"]
        elif "tags" in way and "name" in way["tags"]:
            way_name = way["tags"]["name"]
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
    for (idx, (_id, area)) in enumerate(areas.items(), start=1):
        area_points = area["geometry"]
        area_prop = area["properties"]

        area_center_point = area_prop["area_center_point"]
        min_lon = area_prop["min_lon"]
        min_lat = area_prop["min_lat"]
        max_lon = area_prop["max_lon"]
        max_lat = area_prop["max_lat"]

        area_pokestops = dict()

        if config['pokestop_pokemon']:
            # Get all Pokestops with id, lat and lon
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokestops within min/max lat/lon"))
            pokestop_sel_query = POKESTOP_SELECT_QUERY.format(
                db_name=config['db_r_name'],
                db_pokestop=config['db_pokestop'],
                min_lat=min_lat,
                max_lat=max_lat,
                min_lon=min_lon,
                max_lon=max_lon
            )
            mycursor_r.execute(pokestop_sel_query)
            myresult_pokestops = mycursor_r.fetchall()
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Got all wanted Pokestops - now filter them"))
            for pkstp in myresult_pokestops:
                pkst_point = geometry.Point(pkstp[2], pkstp[1])
                if pkst_point.within(geometry.shape(area_points)):
                    area_pokestops[pkstp[0]] = pkst_point
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Filtering of all Pokestops complete"))

        area_spawnpoints = dict()
        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Get all Spawnpoints within min/max lat/lon"))
        # Get all Spawnpoints with id, lat and lon
        spawnpoint_sel_query = SPAWNPOINT_SELECT_QUERY.format(
            db_name=config['db_r_name'],
            db_spawnpoint=config['db_spawnpoint'],
            sp_id=config['db_spawnpoint_id'],
            lat=config['db_spawnpoint_lat'],
            lon=config['db_spawnpoint_lon'],
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon
        )
        mycursor_r.execute(spawnpoint_sel_query)
        my_result_spawnpoints = mycursor_r.fetchall()
        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Got all wanted Spawnpoints - now filter them"))
        for spwn in my_result_spawnpoints:
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
        if (len(area_pokestops) < 1) and (
                len(area_spawnpoints) < config['min_spawn']):
            failed_nests["Park has not enough Spawnpoints, ignore it"] += 1
            continue
        spawnpoint_in = "'{}'".format("','".join(str(nr) for nr in area_spawnpoints))
        pokestop_in = "'{}'".format("','".join(str(nr) for nr in area_pokestops))

        # Use data since last change:
        reset_time = int(time.time()) - (config['timespan']*3600)
        # RDM uses pokestop_ids, MAD not
        if config['pokestop_pokemon']:
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokes from stops and spawnpoints within nest area"))
            nest_query = NEST_SELECT_QUERY_STOP
            if not config['use_unix_timestamp']:
                nest_query = NEST_SELECT_QUERY_STOP.replace(
                    "UNIX_TIMESTAMP({pokemon_timestamp})",
                    "{pokemon_timestamp}")
        else:
            _city_progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokes from spawnpoints within nest area"))
            nest_query = NEST_SELECT_QUERY
            if not config['use_unix_timestamp']:
                nest_query = NEST_SELECT_QUERY.replace(
                    "UNIX_TIMESTAMP({pokemon_timestamp})",
                    "{pokemon_timestamp}")

        query = nest_query.format(
            db_name=config['db_r_name'],
            db_pokemon_table=config['db_pokemon'],
            pokemon_timestamp=config['db_pokemon_timestamp'],
            pokestop_in=pokestop_in,
            spawn_id=config['db_pokemon_spawnid'],
            spawnpoint_in=spawnpoint_in,
            nest_mons=str(tuple(nest_mons)),
            reset_time=str(reset_time)
        )

        poke_id = 1
        poke_count = 1
        mycursor_r.execute(query)
        poke_data = mycursor_r.fetchone()
        if poke_data:
            poke_id, poke_count = map(int, poke_data)

        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Got all Pokes from Nest area"))

        # (Area_poke/timespan)*(24/scan_hours)
        poke_avg = round(
            (poke_count / float(config['timespan'])) * (
                24.00 / float(config['scan_hours'])), 2)

        _city_progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Filter and insert Nests"))
        if poke_count < config['min_pokemon']:
            failed_nests["Not enough Pokes in this Area to specify a real Nest"] += 1
            continue
        if poke_avg < config['min_avg_pokemon']:
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

    mydb_r.close()
    mydb_w.close()

    print("\nNest analyzing took {:.2f} minutes".format(
        (time.time() - start_time)/60))
    if all_areas:
        print("All Nests Added ({}):\n############".format(len(all_areas)))
    else:
        print("No Nests Added")
    if failed_nests:
        print("No nest reasons:\n############")
        for (key, value) in failed_nests.items():
            print("{}: {}".format(key, value))
    else:
        print("No false positive Parks")

    def discord_webhook():
        """ Send nest data to discord. """
        # Sort basic areas
        sorted_basic_areas = OrderedDict(sorted(
            areas_basic.items(),
            key=lambda kv: kv[1][config["dc-sort-by"]],
            reverse=config["dc-sort-reverse"]))
        content = defaultdict(str)
        content_page = 0
        for b_area in sorted_basic_areas.values():
            if config['dc-ignore-unnamed'] and (b_area["name"] == config["default_park_name"]):
                continue
            if float(b_area["pokemon_avg"]) < config["dc-min-spawns-for-post"]:
                continue
            nest_time = datetime.utcfromtimestamp(
                int(b_area["current_time"])).strftime('%Y-%m-%d %H:%M:%S')
            park_name = b_area["name"]

            g_map_ref = '<https://maps.google.com/maps?q={lon:.5f},{lat:.5f}>'.format(
                lat=b_area["lat"],
                lon=b_area["lon"]
                )
            g_maps = "[Google Maps]({})".format(g_map_ref)
            park_name_g = u"[{name}]({map_ref})".format(
                name=park_name,
                map_ref=g_map_ref)

            custom_map_link = '<{map_link}>'.format(
                map_link=config["dc-map-link"])
            custom_map_ref = custom_map_link.format(
                lat=b_area["lat"],
                lon=b_area["lon"])
            m_maps = "[Map Link]({})".format(custom_map_ref)
            park_name_m = u"[{name}]({map_ref})".format(
                name=park_name,
                map_ref=custom_map_ref)

            poke_shiny = ""
            if b_area["pokemon_shiny"]:
                poke_shiny = locale["poke-shiny-emoji"] + " "
            # convert types:
            poke_type_emojis = list()
            for typ in b_area["pokemon_type"]:
                poke_type_emojis.append(locale["poke-type-emoji"][typ])
            text = (config["dc-text"] + u"\n").format(
                park_name=park_name,
                park_name_g=park_name_g,
                park_name_m=park_name_m,
                poke_id=b_area["pokemon_id"],
                poke_name=b_area["pokemon_name"],
                poke_shiny=poke_shiny,
                poke_avg=b_area["pokemon_avg"],
                poke_type="/".join(b_area["pokemon_type"]),
                poke_type_emoji="/".join(poke_type_emojis),
                time=nest_time,
                g_maps=g_maps,
                m_maps=m_maps
            )
            if len(content[content_page] + text) < DISCORD_MAX_MSG:
                content[content_page] += text
            else:
                content_page += 1
                content[content_page] += text

        def send_webhook(payload):
            """ Send payload to webhook. """
            webhooks = json.loads(config["dc-webhook"])
            if not isinstance(webhooks, list):
                webhooks = [webhooks]
            for webhook in webhooks:
                result = requests.post(
                    webhook,
                    data=json.dumps(payload),
                    headers={"Content-Type": "application/json"})

                if result.status_code > 300:
                    print("Error while sending Webhook")
                    print(result.text)
                time.sleep(DISCORD_RATE_LIMIT)

        # Send Title of Nest Data:
        nest_title = config["dc-title"].format(
            area_name=config["area_name"]
        ) + "\n"
        nest_title += ("-"*len(nest_title))
        payload = {
            "username": config["dc-username"],
            "content": nest_title
            }
        send_webhook(payload)

        # Send Nest Data
        for cont in content.values():
            payload = {
                "username": config["dc-username"],
                "content": cont
            }
            send_webhook(payload)


    if config["dc-enabled"]:
        discord_webhook()

    if config['geojson_extend']:
        with open(config['save_path'], 'r') as old_file_:
            old_geojson = json.load(old_file_)
            all_areas += old_geojson['features']
            print('old areas added to the new ones')
    with open(config['save_path'], 'w') as file_:
        print('write geojson')
        file_.write(dumps(FeatureCollection(all_areas), indent=4))
        print("geoJSON saved successfully")

    with io.open(area_file_name, mode='w', encoding=config["encoding"]) as area_file:
        print("writing area data file...")
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
        print("area data file saved successfully")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", default="default.ini", help="Config file to use")
    args = parser.parse_args()
    config_path = args.config
    config = create_config(config_path)
    print_configs(config)
    analyze_nest_data(config)
