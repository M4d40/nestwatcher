import json
import argparse
import requests
import discord
import time
import sys
import math

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
parser.add_argument("-ne", "--noevents", action='store_true', help="Ignore event data")
parser.add_argument("-nd", "--nodelete", action='store_true', help="Don't delete nests")
args = parser.parse_args()
config_path = args.config
config = Config(config_path)

# Auto migration time
if config.auto_time:
    last_migration_timestamp = requests.get("https://raw.githubusercontent.com/ccev/pogoinfo/info/last-nest-migration").text
    last_migration = datetime.fromtimestamp(int(last_migration_timestamp)) 
    td = datetime.utcnow() - last_migration

    local_time = datetime.now()
    events = requests.get("https://raw.githubusercontent.com/ccev/pogoinfo/info/events/all.json").json()
    for event in events:
        if not event["type"] == "Event":
            continue
        if event["start"] is None:
            continue
        event_start = datetime.strptime(event["start"], "%Y-%m-%d %H:%M")
        if event_start > local_time:
            continue
        event_end = datetime.strptime(event["end"], "%Y-%m-%d %H:%M")
        
        if event_end <= last_migration:
            continue
        
        if event_end < local_time:
            td = local_time - event_end
            log.info(f"Overwriting nest migration with the end time of {event['name']}")
        else:
            td = local_time - event_start
            log.info(f"Overwriting nest migration with the start time of {event['name']}")

    days, seconds = td.days, td.seconds
    config.hours_since_change = math.floor(days * 24 + seconds / 3600)
    log.success(f"Hours since last migration: {config.hours_since_change}")

if args.hours is not None:
    config.hours_since_change = int(args.hours)
    log.info(f"Overwriting hours since change with {config.hours_since_change}")
if args.noevents:
    config.use_events = False

with open("config/areas.json", "r") as area_file:
    areas = json.load(area_file)
with open("config/settings.json", "r") as settings_file:
    settings = json.load(settings_file)

if args.area is not None:
    args.nodelete = True
    areas = [a for a in areas if a["name"] == args.area]
    if len(areas) == 0:
        log.error("Couldn't find that area. Maybe check capitalization")
        sys.exit()

reset_time = int(time.time()) - (config.hours_since_change*3600)

defaults = {
    "min_pokemon": 9,
    "min_spawnpoints": 2,
    "min_average": 0.5,
    "min_ratio": 0,
    "scan_hours_per_day": 24,
    "max_markers": 30,
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

# Event Data

event_mons = []
if config.use_events:
    event = requests.get("https://raw.githubusercontent.com/ccev/pogoinfo/info/events/active.json").json()
    if datetime.strptime(event["end"], "%Y-%m-%d %H:%M") > datetime.now():
        log.success(f"Found ongoing event: {event['name']}")
        log.debug(event)
        for mon in event["details"]["spawns"]:
            try:
                event_mons.append(str(int(mon.split("_")[0])))
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
log.info("Establishing DB connection")
queries = Queries(config)

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
    nests = analyze_nests(config, area_, nest_mons, queries, reset_time, args.nodelete)
    area_.nests = nests
    full_areas.append(area_)

    for nest in nests:
        all_features.append(nest.feature)

with open(config.json_path, "w+") as file_:
    file_.write(dumps(FeatureCollection(all_features), indent=4))
    log.info("Saved Geojson file")
queries.close()

# Discord stuff

discord_webhook_data = []
discord_message_data = []     

for area in full_areas:
    if len(area.nests) == 0:
        log.warning(f"Did not find any nests in {area.name} - Skipping notifications")
        continue
    d = area.settings["discord"]
    if isinstance(d, str):
        if "webhooks" in d:
            embed_dict, entry_list = area.get_nest_text(config)
            discord_webhook_data.append([embed_dict, entry_list, d, area])
    elif isinstance(d, int):
        discord_message_data.append([d, area])


if len(discord_message_data) > 0:
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
            for d, area in discord_message_data:
                """if len(config.emote_server) > 0:
                    log.info("Createing emotes")
                    server = await bot.fetch_guild(config.emote_server)
                    for mon_id in [nest.mon_id for nest in [area.nests for area in full_areas][0]]:
                        emote_name = f"m{mon_id}"
                        image_url = config.icon_repo + f"pokemon_icon_{str(mon_id).zfill(3)}_00.png"
                        image = requests.get(image_url).content

                        emote = await server.create_custom_emoji(name=emote_name, image=image)
                        emote_refs[mon_id] = emote.id"""
                channel = await bot.fetch_channel(d)
                found = False
                embed_dict, _ = area.get_nest_text(config, emote_refs)
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

if len(discord_webhook_data) > 0:
    log.info("Sending webhooks")

    for embed_dict, entry_list, webhook_link, area in discord_webhook_data:
        entry_list_2 = []
        entries = []

        while len(entry_list) > 0:
            text = ""
            for entry in entry_list:
                if len(entry+text) > 2048:
                    entries.append(text)
                    break
                text += entry
                entry_list_2.append(entry)
            entry_list = [e for e in entry_list if e not in entry_list_2]
        if text not in entries:
            entries.append(text)


        for i, entry in enumerate(entries):
            embed = {
                "description": entry
            }
            keys = ["color"]
            if i == 0:
                keys += ["title", "url", "thumbnail", "author"]
            if i == len(entries) - 1:
                keys += ["timestamp", "footer", "image"]
            for key in keys:
                if key in embed_dict.keys():
                    embed[key] = embed_dict[key]
        
            r = requests.post(webhook_link, json={"embeds": [embed]})
            log.success(f"Sent Webhook for {area.name} ({r.status_code})")
            time.sleep(1)


log.success("All done.")