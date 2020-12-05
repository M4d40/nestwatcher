import requests
import time
import json
import timeit

from utils.logging import log

def fetch_data(bbox, date):
    data = """
    [out:json]
    [date:"{date}"]
    [timeout:100000]
    [bbox:{bbox}];
    (
        way[leisure=park];
        way[landuse=recreation_ground];
        way[leisure=recreation_ground];
        way[leisure=pitch];
        way[leisure=garden];
        way[leisure=golf_course];
        way[leisure=playground];
        way[landuse=meadow];
        way[landuse=grass];
        way[landuse=greenfield];
        way[natural=scrub];
        way[natural=heath];
        way[natural=grassland];
        way[landuse=farmyard];
        way[landuse=vineyard];
        way[landuse=farmland];
        way[landuse=orchard];
        way[natural=plateau];
        way[natural=moor];
        
        rel[leisure=park];
        rel[landuse=recreation_ground];
        rel[leisure=recreation_ground];
        rel[leisure=pitch];
        rel[leisure=garden];
        rel[leisure=golf_course];
        rel[leisure=playground];
        rel[landuse=meadow];
        rel[landuse=grass];
        rel[landuse=greenfield];
        rel[natural=scrub];
        rel[natural=heath];
        rel[natural=grassland];
        rel[landuse=farmyard];
        rel[landuse=vineyard];
        rel[landuse=farmland];
        rel[landuse=orchard];
        rel[natural=plateau];
        rel[natural=moor];
    );
    out body;
    >;
    out skel qt;

    """

    data = data.format(bbox=bbox, date=date)

    r = requests.post("http://overpass-api.de/api/interpreter", data=data)
    try:
        return r.json()
    except:
        return {"remark": r.content}

def get_osm_data(bbox, date, osm_file_name):
    got_data = False
    while not got_data:
        free_slot = False
        while not free_slot:
            r = requests.get("http://overpass-api.de/api/status").text
            if "available now" in r:
                free_slot = True
            else:
                if "Slot available after" in r:
                    rate_seconds = int(r.split(", in ")[1].split(" seconds.")[0]) + 15
                    log.warning(f"Overpass is rate-limiting you. Gonna have to wait {rate_seconds} seconds before continuing")
                    time.sleep(rate_seconds)
                else:
                    log.warning("Had trouble finding out about your overpass status. Waiting 1 minute before trying again")
                    time.sleep(60)

        log.info("Getting OSM data. This will take ages if this is your first run.")
        osm_time_start = timeit.default_timer()
        nest_json = fetch_data(bbox, date)
        osm_time_stop = timeit.default_timer()
        seconds = round(osm_time_stop - osm_time_start, 1)
        if len(nest_json.get("elements", [])) == 0:
            log.error(f"Did not get any data from overpass in {seconds} seconds. This probably means that you were rate-limited by overpass. Sleeping 5 minutes and trying again.\nIf you want, you can share the below log entry in Discord")
            log.error(nest_json.get("remark"))
            time.sleep(60*5)
        else:
            got_data = True
            with open(osm_file_name, mode='w', encoding="utf-8") as osm_file:
                osm_file.write(json.dumps(nest_json, indent=4))
            log.success(f"Done. Got all OSM data in {seconds} seconds and saved it.")
    return nest_json