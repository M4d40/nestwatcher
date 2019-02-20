"""
Script to analyze Nests in combination with db and OSM data.
It inserts the Nests inside the db so PMSF can show them.

Original Creator racinel200 and abakedapplepie
Refactored by M4d40
"""

import json
import time

import requests

from shapely import geometry
from mysql import connector

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote


####################
### Config Start ###
####################

TIMESPAN_SINCE_CHANGE = 24  # Timespan in hours
MIN_POKEMON_NEST_COUNT = 10  # Min amount a poke must be spawned in nest area
DELETE_OLD_NESTS = True  # Delete old Nests from db, before inserting new ones


# Area #
########
# point1 -> lower left point
POINT1_LAT = "0.360852"
POINT1_LON = "0.925244"

# point 2 -> upper right point
POINT2_LAT = "0.446112"
POINT2_LON = "0.061136"


# DB Config #
#############
# READ DB
DB_R_HOST = "0.0.0.0"
DB_R_NAME = "rdm"
DB_R_USER = "dbuser"
DB_R_PASS = "dbpass"
DB_R_PORT = 3306
DB_R_TABLE_POKEMON = "pokemon"
DB_R_TABLE_POKESTOP = "pokestop"
DB_R_SPAWNPOINT = "spawnpoint"

# WRITE DB
DB_W_HOST = "0.0.0.0"
DB_W_NAME = "rdm"
DB_W_USER = "dbuser"
DB_W_PASS = "dbpass"
DB_W_PORT = 3306
DB_W_TABLE_NESTS = "nests"


##################
### Config End ###
##################

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
print("\nFollowing Configs will be used:")
print("-"*15)
print("{} hours will be used as timespan".format(TIMESPAN_SINCE_CHANGE))
print("Minimum amount of pokes to count as Nest: {}".format(MIN_POKEMON_NEST_COUNT))
print("Delete Old Nests from DB: {}".format(str(DELETE_OLD_NESTS)))
print("~"*15)

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

POKESTOP_SELECT_QUERY = "SELECT id, lat, lon FROM {db_name}.{db_pokestop}"
SPAWNPOINT_SELECT_QUERY = "SELECT id, lat, lon FROM {db_name}.{db_spawnpoint}"
NEST_SELECT_QUERY = """SELECT pokemon_id, COUNT(pokemon_id) AS count
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
    first_seen_timestamp >= {reset_time})
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

def analyze_nest_data():

    nest_url = osm_uri(POINT1_LAT, POINT1_LON, POINT2_LAT, POINT2_LON)
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
        for node in NestObjectJson[n2]['nodes']:
            NestObjectJson[n2]['ShapelyPoly'] = geometry.MultiPoint(NestObjectJson[n2]['PolyPoints']).convex_hull
        centerp = NestObjectJson[n2]['ShapelyPoly'].centroid
        NestObjectJson[n2]['CenterLat'] = str(centerp.x)
        NestObjectJson[n2]['CenterLon'] = str(centerp.y)
    mydb_r = connector.connect(
        host=DB_R_HOST,
        user=DB_R_USER,
        passwd=DB_R_PASS,
        database=DB_R_NAME,
        port=DB_R_PORT)
    mydb_w = connector.connect(
        host=DB_W_HOST,
        user=DB_W_USER,
        passwd=DB_W_PASS,
        database=DB_W_NAME,
        port=DB_W_PORT)

    mycursor_r = mydb_r.cursor()
    mycursor_w = mydb_w.cursor()

    # Delete old Nest data
    if DELETE_OLD_NESTS:
        mycursor_w.execute(
            NEST_DELETE_QUERY.format(
                db_name=DB_W_NAME,
                db_nests=DB_W_TABLE_NESTS
            )
        )

    # Get all Pokestops with id, lat and lon
    mycursor_r.execute(
        POKESTOP_SELECT_QUERY.format(
            db_name=DB_R_NAME,
            db_pokestop=DB_R_TABLE_POKESTOP
        )
    )
    myresult_pokestops = mycursor_r.fetchall()

    # Get all Spawnpoints with id, lat and lon
    mycursor_r.execute(
        SPAWNPOINT_SELECT_QUERY.format(
            db_name=DB_R_NAME,
            db_spawnpoint=DB_R_SPAWNPOINT
        )
    )
    myresultSpawnPoints = mycursor_r.fetchall()


    for pkstp in myresult_pokestops:
        pkstpPoint = geometry.Point(pkstp[1], pkstp[2])
        all_pokestops[pkstp[0]] = pkstpPoint

    for spwn in myresultSpawnPoints:
        spwnPoint = geometry.Point(spwn[1], spwn[2])
        all_spawn_points[spwn[0]] = spwnPoint


    for nst in NestObjectJson:
        print("Getting spawn point and pokestop data for nest")
        for pkstpKey, pkstp in all_pokestops.items():
            if pkstp.within(NestObjectJson[nst]['ShapelyPoly']):
                NestObjectJson[nst]['PokeStops'].append(pkstpKey)
        for spwnKey, spwn in all_spawn_points.items():
            if spwn.within(NestObjectJson[nst]['ShapelyPoly']):
                NestObjectJson[nst]['SpawnPoints'].append(spwnKey)


    nest_mons = ""
    if len(NEST_SPECIES_LIST) > 0:
        for i in NEST_SPECIES_LIST:
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
        reset_time = int(time.time()) - (TIMESPAN_SINCE_CHANGE*3600)

        query = NEST_SELECT_QUERY.format(
            db_name=DB_R_NAME,
            db_pokemon_table=DB_R_TABLE_POKEMON,
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
            if NestObjectJson[x]['PokemonSpawns'][0][1] >= MIN_POKEMON_NEST_COUNT:
                print("Found Probable Nest")
                # Insert Nest data to db
                sql = NEST_INSERT_QUERY.format(
                    db_name=DB_W_NAME,
                    db_nests=DB_W_TABLE_NESTS,
                    nest_id=str(NestObjectJson[x]['id']),
                    center_lat=str(NestObjectJson[x]['CenterLat']),
                    center_lon=str(NestObjectJson[x]['CenterLon']),
                    poke_id=str(NestObjectJson[x]['PokemonSpawns'][0][0]),
                    type_=0,
                    poke_count=str(NestObjectJson[x]['PokemonSpawns'][0][1]),
                    current_time=current_time
                )
                print(sql)
                mycursor_w.execute(sql)

    mydb_r.commit()
    mydb_r.close()
    mydb_w.commit()
    mydb_w.close()



    f = open("NestObjectJson.json", "w")
    f.write(str(NestObjectJson))
    f.close()

    #PrettyJson = json.dumps(NodeObjectJson, indent=4, sort_keys=False)


if __name__ == "__main__":

    analyze_nest_data()
