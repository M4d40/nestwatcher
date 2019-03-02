"""
Script to analyze Nests in combination with db and OSM data.
It inserts the Nests inside the db so PMSF can show them.

Original Creator racinel200 and abakedapplepie
Refactored by M4d40
"""

import argparse
import json
import time

import requests

from shapely import geometry
from mysql import connector
from geojson import (
    dumps as geodumps,
    dump as geodump,
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
OSM_DATE = "2018-04-09T01:32:00Z"
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



# Show configs

#nest_json = dict()
all_pokestops = dict()
all_spawn_points = dict()


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
    387, 390, 393, 399
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
SPAWNPOINT_SELECT_QUERY = """SELECT {sp_id}, lat, lon FROM {db_name}.{db_spawnpoint}
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
        spawn_id in ({spawnpoint_in})
    )
    AND
    pokemon_id in ({nest_mons})
    AND
    {pokemon_timestamp} >= {reset_time})
GROUP BY pokemon_id
ORDER BY count desc """
NEST_SELECT_QUERY_STOP = """SELECT pokemon_id, COUNT(pokemon_id) AS count
FROM {db_name}.{db_pokemon_table}
WHERE (
    (
        pokestop_id IN ({pokestop_in})
        OR
        spawn_id in ({spawnpoint_in})
    )
    AND
    pokemon_id in ({nest_mons})
    AND
    {pokemon_timestamp} >= {reset_time})
GROUP BY pokemon_id
ORDER BY count desc """
NEST_DELETE_QUERY = "DELETE FROM {db_name}.{db_nests}"
NEST_INSERT_QUERY = """INSERT INTO {db_name}.{db_nests} (
    nest_id, lat, lon, pokemon_id, type, pokemon_count, updated)
VALUES(
    '{nest_id}','{center_lat}','{center_lon}',
    '{poke_id}', {type_}, {poke_count}, {current_time})
ON DUPLICATE KEY UPDATE
    pokemon_id = '{poke_id}',
    type = {type_},
    pokemon_count = {poke_count},
    updated = '{current_time}'
"""


def create_config(config_path):
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
    config['db_pokemon'] = config_raw.get(
        'DB Read',
        'TABLE_POKEMON')
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
    config['db_nest'] = config_raw.get(
        'DB Write',
        'TABLE_NESTS')
    config['save_path'] = config_raw.get(
        'Geojson',
        'SAVE_PATH')
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
        print("")
        print("DB Read:")
        print("Host: {}".format(config['db_w_host']))
        print("Name: {}".format(config['db_w_name']))
        print("User: {}".format(config['db_w_user']))
        print("Password: {}".format(config['db_w_pass']))
        print("Port: {}".format(config['db_w_port']))
    print("~"*15)


def osm_uri(p1_lat, p1_lon, p2_lat, p2_lon):
    """Generate the OSM uri for the OSM data"""
    osm_bbox = "[bbox:{p1_lat},{p1_lon},{p2_lat},{p2_lon}]".format(
        p1_lat=p1_lat,
        p1_lon=p1_lon,
        p2_lat=p2_lat,
        p2_lon=p2_lon
    )
    osm_data = "?data="
    osm_type = "[out:json]"
    date = '[date:"{osm_date}"];'.format(osm_date=OSM_DATE)
    tag_data = OSM_TAGS.replace("\n", "")
    osm_tag_data = "({osm_tags});".format(osm_tags=tag_data)
    osm_end = "out;>;out skel qt;"
    uri = OSM_API + osm_data + quote(osm_type + osm_bbox + date + osm_tag_data + osm_end)
    return uri


def analyze_nest_data(config):

    nest_url = osm_uri(
        config['p1_lat'],
        config['p1_lon'],
        config['p2_lat'],
        config['p2_lon']
    )
    print("Overpass url:")
    print(nest_url)
    osm_session = requests.Session()

    response = osm_session.get(nest_url)

    # global nest_json
    nest_json = json.loads(response.text)
    if not nest_json:
        print("Error getting osm data")
        print(nest_json)
        return

    NestObjectJson = dict()
    NodeObjectJson = dict()
    #print(response.text)
    park_polys = dict()
    nest_polys = list()

    for n in nest_json['elements']:
        if 'nodes' in n:
            NestObjectJson[n['id']] = n
            NestObjectJson[n['id']]['PolyPoints'] = list()
            NestObjectJson[n['id']]['ShapelyPoly'] = ""
            NestObjectJson[n['id']]['PokeStops'] = list()
            NestObjectJson[n['id']]['SpawnPoints'] = list()
            NestObjectJson[n['id']]['PokemonSpawns'] = list()
            NestObjectJson[n['id']]['CenterPoint'] = ""
            NestObjectJson[n['id']]['CenterLat'] = ""
            NestObjectJson[n['id']]['CenterLon'] = ""

        if 'lat' in n:
            NodeObjectJson[n['id']] = n
            vars = n['lat'], n['lon']
            #print(vars)
            NodeObjectJson[n['id']]['LatLon'] = vars


    for n2 in NestObjectJson:
        for node in NestObjectJson[n2]['nodes']:
            NestObjectJson[n2]['PolyPoints'].append(NodeObjectJson[node]['LatLon'])

    for n2 in NestObjectJson:
        for (lat, lon) in NestObjectJson[n2]['PolyPoints']:
            (lon, lat)
        #n2_poly = Polygon(NestObjectJson[n2]['PolyPoints'])
        n2_poly = Polygon([list((lon,lat) for (lat, lon) in NestObjectJson[n2]['PolyPoints'])])
        n2_poly_props = {
            "stroke": config["json-stroke"],
            "stroke-width": config['json-stroke-width'],
            "stroke-opacity": config['json-stroke-opacity'],
            "fill": config['json-fill'],
            "fill-opacity": config['json-fill-opacity']
        }
        park_polys[n2] = Feature(geometry=n2_poly, id=n2, properties=n2_poly_props)
        for node in NestObjectJson[n2]['nodes']:
            NestObjectJson[n2]['ShapelyPoly'] = geometry.MultiPoint(NestObjectJson[n2]['PolyPoints']).convex_hull
        centerp = NestObjectJson[n2]['ShapelyPoly'].centroid
        NestObjectJson[n2]['CenterLat'] = str(centerp.x)
        NestObjectJson[n2]['CenterLon'] = str(centerp.y)
    print("Connect/Start DB Session")
    mydb_r = connector.connect(
        host=config['db_r_host'],
        user=config['db_r_user'],
        passwd=config['db_r_pass'],
        database=config['db_r_name'],
        port=config['db_r_port'])
    mydb_w = connector.connect(
        host=config['db_w_host'],
        user=config['db_w_user'],
        passwd=config['db_w_pass'],
        database=config['db_w_name'],
        port=config['db_w_port'])

    mycursor_r = mydb_r.cursor()
    mycursor_w = mydb_w.cursor()
    print("Connection clear, start doing db stuff")
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

    if config['pokestop_pokemon']:
        # Get all Pokestops with id, lat and lon
        mycursor_r.execute(
            POKESTOP_SELECT_QUERY.format(
                db_name=config['db_r_name'],
                db_pokestop=config['db_pokestop'],
                min_lat=config['p1_lat'],
                max_lat=config['p2_lat'],
                min_lon=config['p1_lon'],
                max_lon=config['p2_lon']
            )
        )
        myresult_pokestops = mycursor_r.fetchall()

        for pkstp in myresult_pokestops:
            pkstpPoint = geometry.Point(pkstp[1], pkstp[2])
            all_pokestops[pkstp[0]] = pkstpPoint

    # Get all Spawnpoints with id, lat and lon
    mycursor_r.execute(
        SPAWNPOINT_SELECT_QUERY.format(
            db_name=config['db_r_name'],
            db_spawnpoint=config['db_spawnpoint'],
            sp_id=config['db_spawnpoint_id'],
            lat=config['db_spawnpoint_lat'],
            lon=config['db_spawnpoint_lon'],
            min_lat=config['p1_lat'],
            max_lat=config['p2_lat'],
            min_lon=config['p1_lon'],
            max_lon=config['p2_lon']
        )
    )
    myresultSpawnPoints = mycursor_r.fetchall()

    for spwn in myresultSpawnPoints:
        spwnPoint = geometry.Point(spwn[1], spwn[2])
        all_spawn_points[spwn[0]] = spwnPoint


    for nst in NestObjectJson:
        print("Getting spawn point and pokestop data for nest")
        if config['pokestop_pokemon']:
            for pkstpKey, pkstp in all_pokestops.items():
                if pkstp.within(NestObjectJson[nst]['ShapelyPoly']):
                    NestObjectJson[nst]['PokeStops'].append(pkstpKey)
        for spwnKey, spwn in all_spawn_points.items():
            if spwn.within(NestObjectJson[nst]['ShapelyPoly']):
                NestObjectJson[nst]['SpawnPoints'].append(spwnKey)


    nest_mons = ""
    if len(NEST_SPECIES_LIST) > 0:
        filtered_species = set(NEST_SPECIES_LIST) - set(config['event_poke'])
        for i in filtered_species:
            if nest_mons == "":
                nest_mons = "'"+ str(i) +"'"
            else:
                nest_mons = nest_mons + ",'"+ str(i) +"'"
    else:
        nest_mons = "''"

    print(NestObjectJson)
    for nst in NestObjectJson:
        pokestop_in = ""
        spawnpoint_in = ""

        if len(NestObjectJson[nst]['PokeStops']) < 1 and len(NestObjectJson[nst]['SpawnPoints']) < 1:
            continue

        if len(NestObjectJson[nst]['PokeStops']) > 0:
            for i in NestObjectJson[nst]['PokeStops']:
                pokestop_in = pokestop_in + ",'"+ str(i) +"'"
            pokestop_in = pokestop_in[1:]
        else:
            pokestop_in = "''"
        if len(NestObjectJson[nst]['SpawnPoints']) > 0:
            for i in NestObjectJson[nst]['SpawnPoints']:
                spawnpoint_in = spawnpoint_in + ",'"+ str(i) +"'"
            spawnpoint_in = spawnpoint_in[1:]
        else:
            spawnpoint_in = "''"

        #print(spawnpoint_in)
        #print(pokestop_in)
        #print(nest_mons)

        # Use data since last change:
        reset_time = int(time.time()) - (config['timespan']*3600)
        # RDM uses pokestop_ids, MAD not
        if config['pokestop_pokemon']:
            nest_query = NEST_SELECT_QUERY_STOP
        else:
            nest_query = NEST_SELECT_QUERY
        query = nest_query.format(
            db_name=config['db_r_name'],
            db_pokemon_table=config['db_pokemon'],
            pokemon_timestamp=config['db_pokemon_timestamp'],
            pokestop_in=pokestop_in,
            spawnpoint_in=spawnpoint_in,
            nest_mons=nest_mons,
            reset_time=str(reset_time)
        )
        print(query)
        mycursor_r.execute(query)
        myresult = mycursor_r.fetchall()

        for mrsp in myresult:
            rt = mrsp[0], mrsp[1]
            NestObjectJson[nst]['PokemonSpawns'].append(rt)


    current_time = int(time.time())

    for x in NestObjectJson:
        if len(NestObjectJson[x]['PokemonSpawns']) > 2:
            if NestObjectJson[x]['PokemonSpawns'][0][1] >= config['min_pokemon']:
                nest_polys.append(park_polys[NestObjectJson[x]['id']])
                print("Found Probable Nest")
                # Insert Nest data to db
                sql = NEST_INSERT_QUERY.format(
                    db_name=config['db_w_name'],
                    db_nests=config['db_nest'],
                    nest_id=str(NestObjectJson[x]['id']),
                    center_lat=str(NestObjectJson[x]['CenterLat']),
                    center_lon=str(NestObjectJson[x]['CenterLon']),
                    poke_id=str(NestObjectJson[x]['PokemonSpawns'][0][0]),
                    type_=0,
                    poke_count=(NestObjectJson[x]['PokemonSpawns'][0][1] / config['timespan']),
                    current_time=current_time
                )
                print(sql)
                mycursor_w.execute(sql)

    mydb_r.commit()
    mydb_r.close()
    mydb_w.commit()
    mydb_w.close()



    #f = open(config['save_path'], "w")
    #f.write(str(NestObjectJson))
    #f.write(json.dumps(FeatureCollection(nest_polys), indent=4, sort_keys=True))
    #f.close()
    with open(config['save_path'], "w") as file_:
        json.dump(FeatureCollection(nest_polys), file_, indent=4)

    #PrettyJson = json.dumps(NodeObjectJson, indent=4, sort_keys=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="default.ini",
        help="Config file to use")
    args = parser.parse_args()
    config_path = args.config
    config = create_config(config_path)
    print_configs(config)
    analyze_nest_data(config)
