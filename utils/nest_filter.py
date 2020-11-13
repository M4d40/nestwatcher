import json
import time

from utils.area import RelPark

def nest_filter(args):
    progress = args[0]
    check_nest_task = args[1]
    failed_nests = args[2]
    park = args[3]
    area = args[4]
    config = args[5]
    queries = args[6]
    all_mons = args[7]
    all_spawns = args[8]
    nest_mons = args[9]
    reset_time = args[10]
    double_ways = args[11]
    area_file_data = args[12]
    progress.update(check_nest_task, advance=1, description=f"Nests found: {failed_nests['Total Nests found']}")

    if not park.is_valid:
        failed_nests["Geometry is not valid"] += 1
        return

    if not area.polygon.contains(park.polygon):
        failed_nests["Not in Geofence"] += 1
        return

    pokestop_in = None
    stops = []
    if config.scanner == "rdm" and config.pokestop_pokemon:
        # Get all Pokestops with id, lat and lon
        for pkstp in queries.stops(park.sql_fence):
            stops.append(str(pkstp[0]))
        pokestop_in = "'{}'".format("','".join(stops))

    if config.less_queries:
        spawns = [s[0] for s in all_spawns if park.polygon.contains(s[1])]
    else:
        spawns = [str(s[0]) for s in queries.spawns(park.sql_fence)]

    if not stops and not spawns:
        failed_nests["No Stops or Spawnpoints"] += 1
        return
    if (len(stops) < 1) and (len(spawns) < area.settings['min_spawnpoints']):
        failed_nests["Not enough Spawnpoints"] += 1
        return
    spawnpoint_in = "'{}'".format("','".join(spawns))
    if spawnpoint_in == "''": spawnpoint_in = "NULL" # This will handle the SQL warning since a blank string shouldn't be used for a number

    if config.less_queries:
        mons = [s[0] for s in all_mons if park.polygon.contains(s[1])]
        if len(mons) == 0:
            failed_nests["No Pokemon"] += 1
            return
        most_id = max(set(mons), key=mons.count)
        poke_data = [most_id, mons.count(most_id)]

    else:
        poke_data = queries.mons(spawnpoint_in, str(tuple(nest_mons)), str(reset_time), pokestop_in)

        if poke_data is None:
            failed_nests["No Pokemon"] += 1
            return
    park.mon_data(poke_data[0], poke_data[1], area.settings['scan_hours_per_day'], len(spawns) + len(stops))

    if park.mon_count < area.settings['min_pokemon']:
        failed_nests["Not enough Pokemon"] += 1
        return
    if park.mon_avg < area.settings['min_average']:
        failed_nests["Average spawnrate too low"] += 1
        return
    if park.mon_ratio < area.settings['min_ratio']:
        failed_nests["Average spawn ratio too low"] += 1
        return
    if park.id in double_ways:
        failed_nests["Avoiding double nests"] += 1
        return

    park.generate_details(area_file_data, failed_nests["Total Nests found"])
    failed_nests['Total Nests found'] += 1

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
    queries.nest_insert(insert_args)

    return park