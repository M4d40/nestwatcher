import json
import argparse
import requests
import discord
import time
import sys

from datetime import datetime
from geojson import FeatureCollection, dumps

from utils.area import Area
from utils.analyze import analyze_nests
from utils.config import Config
from utils.logging import log
from utils.queries import Queries
from utils.discord import get_emotes

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--config", default="config/config.ini", help="Config file to use")
parser.add_argument("-t", "--hours", default=None, help="Hours since last migration")
parser.add_argument("-a", "--area", default=None, help="A specific area to analyze")
args = parser.parse_args()
config_path = args.config
config = Config(config_path)
if not args.hours is None:
    config.hours_since_change = int(args.hours)

with open("config/areas.json", "r") as f:
    areas = json.load(f)
with open("config/settings.json", "r") as f:
    settings = json.load(f)

if args.area is not None:
    areas = [a for a in areas if a["name"] == args.area]
    if len(areas) == 0:
        log.error("Couldn't find that area. Maybe check capitalization")
        sys.exit()

reset_time = int(time.time()) - (config.hours_since_change*3600)

discord_webhook = False
discord_message = False

defaults = {
    "min_pokemon": 9,
    "min_spawnpoints": 2,
    "min_average": 0.5,
    "scan_hours_per_day": 24,
    "discord": ""
}
settings_defaults = [s for s in settings if s.get("area") == "DEFAULT"]
if len(settings_defaults) > 0:
    settings_defaults = settings_defaults[0]
else:
    settings_defaults = {}
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

for setting in area_settings.values():
    if isinstance(setting["discord"], str):
        if "webhooks" in setting["discord"]:
            discord_webhook = True
    elif isinstance(setting["discord"], int):
        discord_message = True

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

# Meganests
if config.in_meganest:
    log.info("You're living in a meganest. Getting the mosg scanned mon from your DB and ignoring it for the rest of the run")
    most_mon = str(queries.most_mon(str(tuple(nest_mons)), str(reset_time))[0])
    if most_mon in nest_mons:
        nest_mons.remove(most_mon)

all_features = []
full_areas = []
for i, area in enumerate(areas):
    area_ = Area(area, area_settings[area["name"]])
    nests = analyze_nests(config, area_, nest_mons, queries, reset_time)
    area_.nests = nests
    full_areas.append(area_)

    for nest in nests:
        all_features.append(nest.feature)

with open(config.json_path, "w+") as file_:
    file_.write(dumps(FeatureCollection(all_features), indent=4))
    log.info("Saved Geojson file")
queries.close()

# Discord stuff
if discord_message:
    log.info("Logging into Discord")
    bot = discord.Client()

    @bot.event
    async def on_ready():
        """for guild in bot.guilds:
            if bot.user.id == guild.owner_id:
                await guild.delete()   """  
        try:
            log.info("Connected to Discord. Generating Nest messages and sending them.")
            emote_refs = await get_emotes(bot, nesting_mons, config)
            """if len(config.emote_server) > 0:
                log.info("Createing emotes")
                server = await bot.fetch_guild(config.emote_server)
                for mon_id in [nest.mon_id for nest in [area.nests for area in full_areas][0]]:
                    emote_name = f"m{mon_id}"
                    image_url = config.icon_repo + f"pokemon_icon_{str(mon_id).zfill(3)}_00.png"
                    image = requests.get(image_url).content

                    emote = await server.create_custom_emoji(name=emote_name, image=image)
                    emote_refs[mon_id] = emote.id"""
            for area in full_areas:
                if len(area.nests) == 0:
                    log.warning(f"Did not find any nests in {area.name} - Skipping notifications")
                    continue
                d = area.settings["discord"]
                if isinstance(d, int):
                    channel = await bot.fetch_channel(d)
                    found = False
                    embed_dict = area.get_nest_text(config, emote_refs)
                    embed = discord.Embed().from_dict(embed_dict)
                    async for message in channel.history():
                        if message.author == bot.user:
                            embeds = message.embeds
                            if len(embeds) > 0:
                                if embeds[0].title == embed.title:
                                    found = True
                                    break
                    if found:
                        await message.edit(embed=embed)
                        log.success(f"Found existing Nest message for {area.name} and edited it")
                    else:
                        await channel.send(embed=embed)
                        log.success(f"Sent a new Nest message for {area.name}")
            
            """if len(emote_refs) > 0:
                log.info("Deleting emotes again")
                for emote_id in emote_refs.values():
                    emote = await server.fetch_emoji(emote_id)
                    await emote.delete()"""
        except Exception as e:
            log.exception(e)
        await bot.logout()

    bot.run(config.discord_token)
log.success("All done.")