import json
import time
import timeit
import requests

from rich.progress import Progress
from shapely import geometry
from shapely.ops import polylabel, cascaded_union
from geojson import Feature
from collections import defaultdict

from utils.logging import log
from utils.overpass import get_osm_data
from utils.area import WayPark, RelPark

OSM_DATE = "2019-02-24T00:00:00Z"

def analyze_nests(config, area, nest_mons, queries, reset_time):

    # Getting OSM/overpass data
    
    osm_file_name = f"data/osm_data/{area.name} {OSM_DATE.replace(':', '')}.json"
    try:
        with open(osm_file_name, mode="r", encoding="utf-8") as osm_file:
            nest_json = json.load(osm_file)
    except (IOError, OSError):
        free_slot = False
        while not free_slot:
            r = requests.get("http://overpass-api.de/api/status").text
            if "available now" in r:
                free_slot = True
            else:
                if "Slot available after" in r:
                    rate_seconds = int(r.split(", in ")[1].split(" seconds.")[0]) + 5
                    log.warning(f"Overpass is rate-limiting you. Gonna have to wait {rate_seconds} seconds before continuing")
                    time.sleep(rate_seconds)
                else:
                    log.warning("Had trouble finding out about your overpass status. Waiting 1 minute before trying again")
                    time.sleep(60)

        log.info("Getting OSM data. This will take ages if this is your first run.")
        osm_time_start = timeit.default_timer()
        nest_json = get_osm_data(area.bbox, OSM_DATE)
        osm_time_stop = timeit.default_timer()
        seconds = round(osm_time_stop - osm_time_start, 1)
        if not nest_json["elements"]:
            log.error(f"Did not get any data from overpass in {seconds} seconds. Because of that, the script will now error out. Please try again in a few hours, since you were rate-limited by overpass. If this still doesn't help, try splitting up your area.")
            log.error(nest_json.get("remark"))
            return
        with open(osm_file_name, mode='w', encoding="utf-8") as osm_file:
            osm_file.write(json.dumps(nest_json, indent=4))
        log.success(f"Done. Got all OSM data in {seconds} seconds and saved it.")

    # Getting area data

    area_file_name = f"data/area_data/{area.name}.json"
    area_file_data = {}
    try:
        with open(area_file_name, mode="r", encoding="utf-8") as area_file:
            log.info("Found area data file. Reading and using data from it now")
            area_file_data_raw = json.load(area_file)
        for k, v in area_file_data_raw.items():
            area_file_data[int(k)] = v

    except FileNotFoundError:
        pass

    """db_file_name = f"data/db_data/{area.name}.json"
    try:
        with open(db_file_name, mode="r", encoding="utf-8") as db_file:
            db_data = json.load(db_file)
    except FileNotFoundError:
        db_data = {}"""

    log.info(f"Got all relevant information. Searching for nests in {area.name} now")

    nodes = {}
    ways = []
    relations = []
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
            ways.append(WayPark(element, config))
        elif element["type"] == "relation":
            if "members" not in element and not element["members"]:
                continue
            relations.append(RelPark(element, config))

    parks = ways + relations

    # Check Relations

    failed_nests = defaultdict(int)
    failed_nests["Total Nests found"] = 0
    double_ways = []

    start = timeit.default_timer()
    
    with Progress() as progress:
        check_rels_task = progress.add_task("Generating Polygons", total=len(parks))
        for park in relations:
            double_ways = park.get_polygon(nodes, ways, double_ways)
            progress.update(check_rels_task, advance=1)
        for park in ways:
            park.get_polygon(nodes)
            progress.update(check_rels_task, advance=1)

        for osm_id, data in area_file_data.items():
            for connect_id in data["connect"]:
                for i, park in enumerate(parks):
                    if park.id == osm_id:
                        big_park = park
                        big_park_i = i
                    if park.id == connect_id:
                        small_park = park
                        small_park_i = i

                parks[big_park_i].connect.append(connect_id)
                parks[big_park_i].polygon = cascaded_union([big_park.polygon, small_park.polygon])
                parks.pop(small_park_i)

        # NOW CHECK ALL AREAS ONE AFTER ANOTHER
        check_nest_task = progress.add_task("Nests found: 0", total=len(parks))
        nests = []

        for park in parks:
            progress.update(check_nest_task, advance=1, description=f"Nests found: {failed_nests['Total Nests found']}")

            if not park.is_valid:
                failed_nests["Geometry is not valid"] += 1
                continue

            if not area.polygon.contains(park.polygon):
                failed_nests["Not in Geofence"] += 1
                continue

            pokestop_in = None
            stops = []
            if config.scanner == "rdm" and config.pokestop_pokemon:
                # Get all Pokestops with id, lat and lon
                for pkstp in queries.stops(park.sql_fence):
                    stops.append(str(pkstp[0]))
                pokestop_in = "'{}'".format("','".join(stops))

            spawns = [str(s[0]) for s in queries.spawns(park.sql_fence)]

            if not stops and not spawns:
                failed_nests["No Stops or Spawnpoints"] += 1
                continue
            if (len(stops) < 1) and (len(spawns) < area.settings['min_spawnpoints']):
                failed_nests["Not enough Spawnpoints"] += 1
                continue
            spawnpoint_in = "'{}'".format("','".join(spawns))
            if spawnpoint_in == "''": spawnpoint_in = "NULL" # This will handle the SQL warning since a blank string shouldn't be used for a number

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
            if poke_data is None:
                continue
            park.mon_data(poke_data[0], poke_data[1], area.settings['scan_hours_per_day'], len(spawns) + len(stops))

            if park.mon_count < area.settings['min_pokemon']:
                failed_nests["Not enough Pokemon"] += 1
                continue
            if park.mon_avg < area.settings['min_average']:
                failed_nests["Average spawnrate too low"] += 1
                continue
            if park.mon_ratio < area.settings['min_ratio']:
                failed_nests["Average spawn ratio too low"] += 1
                continue
            if park.id in double_ways:
                failed_nests["Avoiding double nests"] += 1
                continue

            park.generate_details(area_file_data, failed_nests["Total Nests found"])

            # Insert Nest data to db
            insert_args = {
                "nest_id": park.id,
                "name": park.name,
                "form": park.mon_form,
                "lat": park.lat,
                "lon": park.lon,
                "pokemon_id": park.mon_id,
                "type": 0,
                "pokemon_count": park.mon_count,
                "pokemon_avg": park.mon_avg,
                "pokemon_ratio": park.mon_ratio,
                "poly_path": json.dumps(park.path),
                "poly_type": 1 if isinstance(park, RelPark) else 0,
                "current_time": int(time.time())
            }

            failed_nests["Total Nests found"] += 1
            nests.append(park)

            queries.nest_insert(insert_args)
    stop = timeit.default_timer()
    log.success(f"Done finding nests in {area.name} ({round(stop - start, 1)} seconds)")
    for k, v in failed_nests.items():
        log.info(f" - {k}: {v}")

    def sort_avg(nest):
        return nest.mon_avg

    new_area_data = {}
    for nest in sorted(nests, key=sort_avg, reverse=True):
        new_area_data[nest.id] = {
            "name": nest.name,
            "center": [nest.lat, nest.lon],
            "connect": nest.connect
        }
    for oid, data in area_file_data.items():
        if oid not in [n.id for n in nests]:
            new_area_data[oid] = {
                "name": data["name"],
                "center": data["center"],
                "connect": data["connect"]
            }
    with open(area_file_name, mode="w+") as area_file:
        area_file.write(json.dumps(new_area_data, indent=4))

        log.info("Saved area data")
    log.success(f"All done with {area.name}\n")

    return nests