import json
import argparse
import requests
import sys

from datetime import datetime
from geojson import FeatureCollection, dumps

from utils.area import Area
from utils.analyze import analyze_nests
from utils.config import Config
from utils.logging import log
from utils.queries import Queries

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", default="config/config.ini", help="Config file to use")
parser.add_argument("-t", "--hours", default=None, help="Hours since last migration")
args = parser.parse_args()
config_path = args.config
config = Config(config_path)
if not args.hours is None:
    config.hours_since_change = int(args.hours)

with open("config/areas.json", "r") as f:
    areas = json.load(f)
with open("config/settings.json", "r") as f:
    settings = json.load(f)

defaults = {
    "min_pokemon": 9,
    "min_spawnpoints": 2,
    "min_average": 0.5,
    "scan_hours_per_day": 24
}
settings_defaults = [s for s in settings if s.get("area") == "DEFAULT"][0]
for k, v in defaults.items():
    defaults[k] = settings_defaults.get(k, v)

for area in areas:
    if area["name"] not in [s["area"] for s in settings]:
        settings.append({"area": area["name"]})
area_settings = {}
for setting in settings:
    area_settings[setting["area"]] = {}
    for k, v in defaults.items():
        area_settings[setting["area"]][k] = setting.get(k, v)

# Event Data

event_mons = []
event = requests.get("https://raw.githubusercontent.com/ccev/pogoinfo/info/events/active.json").json()
if datetime.strptime(event["end"], "%Y-%m-%d %H:%M") > datetime.now():
    log.success(f"Found ongoing event: {event['name']}")
    log.debug(event)
    for mon in event["details"]["spawns"]:
        try:
            event_mons.append(mon.split("_")[0])
        except:
            pass
    log.debug(f"event mons: {event_mons}")
else:
    log.info("No ongoing event found")

# Getting nesting species

nesting_mons = requests.get("https://pogoapi.net/api/v1/nesting_pokemon.json").json().keys()
nest_mons = [m for m in nesting_mons if m not in event_mons]
log.info("Got all nesting species")
log.debug(nest_mons)

# DB
log.info("Establishing DB connection and deleting current nests")
queries = Queries(config)
queries.nest_delete()

all_nests = []
for area in areas:
    area_ = Area(area, area_settings[area["name"]])
    nests = analyze_nests(config, area_, nest_mons, queries)
    all_nests += (nests)

with open(config.json_path, "w+") as file_:
    file_.write(dumps(FeatureCollection(all_nests), indent=4))
    log.success("Saved Geojson file")