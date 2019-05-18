"""
Script to analyze Nests in combination with db and OSM data.
It inserts the Nests inside the db so PMSF can show them.

Original Creator racinel200 and abakedapplepie
Refactored by M4d40
"""


from collections import defaultdict

import argparse
import json
import sys
import time

import requests

from shapely import geometry
from pymysql import connect
from geojson import (
    Feature,
    FeatureCollection,
    Polygon
)

# Python2 and Python3 compatibility
try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser
try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote


DEFAULT_CONFIG = "default.ini"

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
    387, 390, 393, 399, 449
]
NEST_SPECIES_LIST = (
    NEST_G1 + NEST_G2 + NEST_G3 + NEST_G4)

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
    pokemon_id IN ({nest_mons})
    AND
    UNIX_TIMESTAMP({pokemon_timestamp}) >= {reset_time})
GROUP BY pokemon_id
ORDER BY count desc """
NEST_SELECT_QUERY_STOP = """SELECT pokemon_id, COUNT(pokemon_id) AS count
FROM {db_name}.{db_pokemon_table}
WHERE (
    (
        pokestop_id IN ({pokestop_in})
        OR
        {spawn_id} IN ({spawnpoint_in})
    )
    AND
    pokemon_id IN ({nest_mons})
    AND
    UNIX_TIMESTAMP({pokemon_timestamp}) >= {reset_time})
GROUP BY pokemon_id
ORDER BY count desc """
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
    config['min_spawn'] = config_raw.getint(
        'Nest Config',
        'MIN_SPAWNPOINT_NEST_COUNT')
    config['delete_old'] = config_raw.getboolean(
        'Nest Config',
        'DELETE_OLD_NESTS')
    config['event_poke'] = json.loads(config_raw.get(
        'Nest Config',
        'EVENT_POKEMON'))
    config['pokestop_pokemon'] = config_raw.getboolean(
        'Nest Config',
        'POKESTOP_POKEMON')
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
    print("-"*15)
    print("{} hours will be used as timespan".format(config['timespan']))
    print("Minimum amount of pokes to count as Nest: {}".format(config['min_pokemon']))
    print("Ignore Event Pokemon: {}".format(str(config['event_poke'])))
    print("Delete Old Nests from DB: {}".format(str(config['delete_old'])))
    print("File will be saved in: {}".format(str(config['save_path'])))
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


def osm_uri(p1_lat, p1_lon, p2_lat, p2_lon, osm_date):
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
    tag_data = OSM_TAGS.replace("\n", "")
    osm_tag_data = "({osm_tags});".format(osm_tags=tag_data)
    osm_end = "out;>;out skel qt;"
    uri = OSM_API + osm_data + quote(osm_type + osm_bbox + date + osm_tag_data + osm_end)
    return uri


def analyze_nest_data(config):
    """ Analyze nest data """
    start_time = time.time()
    nest_url = osm_uri(
        config['p1_lat'],
        config['p1_lon'],
        config['p2_lat'],
        config['p2_lon'],
        config['osm_date'],
    )
    print("Overpass url:")
    print(nest_url)
    print("Getting OSM Data...")
    osm_session = requests.Session()

    response = osm_session.get(nest_url)

    # global nest_json
    nest_json = json.loads(response.text)
    if not nest_json:
        print("Error getting osm data")
        print(nest_json)
        return

    print("Getting OSM Data...Complete (took {} seconds)".format(time.time()))
    nest_mons = ""
    if NEST_SPECIES_LIST:
        filtered_species = set(NEST_SPECIES_LIST) - set(config['event_poke'])
        for i in filtered_species:
            if nest_mons == "":
                nest_mons = "'"+ str(i) +"'"
            else:
                nest_mons = nest_mons + ",'"+ str(i) +"'"
    else:
        nest_mons = "''"
    #print(response.text)
    print("##"*20)

    nodes = dict()
    areas = list()
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
            areas.append(element)
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

    all_areas = list()
    failed_nests = defaultdict(int)
    areas_len = len(areas)
    for (idx, area) in enumerate(areas, start=1):
        area_name = "Unknown Areaname"
        if "tags" in area and "name" in area["tags"]:
            area_name = area["tags"]["name"]
        progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Starting to analyze Nest"))
        area_points = list()
        for point in area['nodes']:
            point_coords = nodes[point]
            area_points.append([point_coords['lon'], point_coords['lat']])
        area_poly = Polygon([area_points])
        area_poly_props = {
            "name": area_name,
            "stroke": config["json-stroke"],
            "stroke-width": config['json-stroke-width'],
            "stroke-opacity": config['json-stroke-opacity'],
            "fill": config['json-fill'],
            "fill-opacity": config['json-fill-opacity']
        }
        area_shapeley_poly = geometry.MultiPoint(area_points).convex_hull
        area_center_point = area_shapeley_poly.centroid
        min_lon, min_lat, max_lon, max_lat = area_shapeley_poly.bounds

        area_pokestops = dict()
        if config['pokestop_pokemon']:
            # Get all Pokestops with id, lat and lon
            progress(idx, areas_len, "({}/{}) {}".format(
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
            #print(pokestop_sel_query)
            mycursor_r.execute(pokestop_sel_query)
            myresult_pokestops = mycursor_r.fetchall()
            progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Got all wanted Pokestops - now filter them"))
            for pkstp in myresult_pokestops:
                pkst_point = geometry.Point(pkstp[2], pkstp[1])
                if pkst_point.within(area_shapeley_poly):
                    area_pokestops[pkstp[0]] = pkst_point
            progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Filtering of all Pokestops complete"))

        area_spawnpoints = dict()
        progress(idx, areas_len, "({}/{}) {}".format(
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
        #print(spawnpoint_sel_query)
        mycursor_r.execute(spawnpoint_sel_query)
        my_result_spawnsoints = mycursor_r.fetchall()
        progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Got all wanted Spawnpoints - now filter them"))
        for spwn in my_result_spawnsoints:
            spwn_point = geometry.Point(spwn[2], spwn[1])
            if spwn_point.within(area_shapeley_poly):
                area_spawnpoints[spwn[0]] = spwn_point
        progress(idx, areas_len, "({}/{}) {}".format(
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
        #print(spawnpoint_in)
        #print(pokestop_in)
        #print(nest_mons)

        # Use data since last change:
        reset_time = int(time.time()) - (config['timespan']*3600)
        # RDM uses pokestop_ids, MAD not
        if config['pokestop_pokemon']:
            progress(idx, areas_len, "({}/{}) {}".format(
                idx,
                areas_len,
                "Get all Pokes from stops and spawnpoints within nest area"))
            nest_query = NEST_SELECT_QUERY_STOP
            if not config['use_unix_timestamp']:
                nest_query = NEST_SELECT_QUERY_STOP.replace(
                    "UNIX_TIMESTAMP({pokemon_timestamp})",
                    "{pokemon_timestamp}")
        else:
            progress(idx, areas_len, "({}/{}) {}".format(
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
            nest_mons=nest_mons,
            reset_time=str(reset_time)
        )
        #print(query)
        mycursor_r.execute(query)
        myresult = mycursor_r.fetchall()
        progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Got all Pokes from Nest area"))
        area_poke = (0, 0)
        for mrsp in myresult:
            poke_id, poke_amount = int(mrsp[0]), int(mrsp[1])
            if poke_amount < area_poke[1]:
                continue
            area_poke = (poke_id, poke_amount)
        progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Filter and insert Nests"))
        if area_poke[1] < config['min_pokemon']:
            failed_nests["Not enough Pokes in this Area to specify a real Nest"] += 1
            continue

        current_time = int(time.time())

        progress(idx, areas_len, "({}/{}) {}".format(
            idx,
            areas_len,
            "Found Probable Nest - insert it now in db"))
        # Insert Nest data to db
        insert_query = NEST_INSERT_QUERY.format(
            db_name=config['db_w_name'],
            db_nests=config['db_nest'])

        insert_args = {
            "nest_id": str(area['id']),
            "name": area_name,
            "lat": float(area_center_point.x),
            "lon": float(area_center_point.y),
            "pokemon_id": int(area_poke[0]),
            "type": 0,
            "pokemon_count": int(area_poke[1]),
            "pokemon_avg": area_poke[1] / float(config['timespan']),
            "current_time": current_time,
        }
        #print(sql)
        mycursor_w.execute(insert_query, insert_args)
        print("\nNest added in DB\n")
        all_areas.append(
            Feature(
                geometry=area_poly,
                id=area['id'],
                properties=area_poly_props))

    mydb_r.close()
    mydb_w.close()

    print("\nNest analyzing took {:.2f} minutes".format(
        (time.time() - start_time)/60))
    if all_areas:
        print("All Nests Added ({}):\n############".format(len(all_areas)))
    else:
        print("No Nests Added")
    print("No nest reasons:\n############") if failed_nests else "No false positive Parks"
    for (key, value) in failed_nests.items():
        print("{}: {}".format(key, value))


    if config['geojson_extend']:
        with open(config['save_path'], 'r') as old_file_:
            old_geojson = json.load(old_file_)
            all_areas += old_geojson['features']
            print('old areas added to the new ones')
    with open(config['save_path'], 'w') as file_:
        print('write geojson')
        json.dump(FeatureCollection(all_areas), file_, indent=4)
        print("geoJSON saved successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", default="default.ini", help="Config file to use")
    args = parser.parse_args()
    config_path = args.config
    config = create_config(config_path)
    print_configs(config)
    analyze_nest_data(config)
