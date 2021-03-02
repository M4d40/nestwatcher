import os
import discord
import csv
import json
import sys
import requests

from configparser import ConfigParser

from nestwatcher.config import Config
from nestwatcher.area import get_zoom, Area
from nestwatcher.queries import Queries

tools = {
    "1": "Update area_data using Discord",
    "2": "Migrate data to a newer version",
    "3": "Update area_data using up-to-date OSM data",
    "4": "Delete all Discord emotes",
    "5": "Fetch OSM data for all areas"
}

print("What are you looking for?")

def list_options(tools):
    for number, name in tools.items():
        print(f" {number}: {name}")
    wanted = input("Type a number: ")
    return wanted

wanted = list_options(tools)

config = Config()

if wanted == "1":
    print("Okay, now put the name of the area you want the bot to go through. Then go to a channel the bot as access to and write 'start', then follow the instructions on Discord.\n\nPlease note that:\n - The bot needs Manage Messages Perms (you may also want to do it in a private channel)\n - You have a tileserver configured")
    areaname = input("Area: ")
    print("Starting the bot now. Please write 'start' and follow your bot's instructions.")

    bot = discord.Client()
    @bot.event
    async def on_message(message):
        if not message.content == "start":
            return
        admin = message.author
        channel = message.channel
        await message.delete()
        queries = Queries(config)

        controls = {
            "📝": "name",
            "🗺️": "point",
            "⏩": "skip",
            "❌": "exit"
        }

        embed = discord.Embed(
            description="This bot will now go through each nest in your database, allowing you to rename and set the marker for each one.\nTo see the changes reflect on your map or Discord, re-run the nest script once.\n\nFor every park there are 3 reactions:\n\n📝 to set a name\n🗺️ to set a point\n⏩ to go to the next park.\n❌ to stop everything\n\nAfter choosing one of the options, you can set the value by sending a message.\n\nPress ✅ to start."
        )
        message = await channel.send(embed=embed)
        await message.add_reaction("✅")

        def check(reaction, user):
            return str(reaction.emoji) == "✅" and user.id == admin.id
        try:
            await bot.wait_for("reaction_add", check=check, timeout=60*60*24)
        except:
            print("Error while trying to check the start reaction")
        else:
            
            await message.clear_reactions()

            for emote in controls.keys():
                await message.add_reaction(emote)

            with open("config/areas.json", "r") as f:
                areas = json.load(f)
                area = Area([a for a in areas if a["name"] == areaname][0], None)

            queries.nest_cursor.execute(f"select nest_id, name, lat, lon, polygon_path, polygon_type from nests WHERE ST_CONTAINS(ST_GEOMFROMTEXT('POLYGON({area.sql_fence})'), point(lat, lon)) order by pokemon_avg desc")
            nests = queries.nest_cursor.fetchall()

            file_name = f"data/area_data/{areaname}.json"
            with open(file_name, "r") as f:
                area_data = json.load(f)

            def get_desc(name, lat, lon, osm_link, g_link):
                return f"Name: **{name}**\nCenter: `{round(lat, 5)},{round(lon, 6)}`\n\n[OSM Link]({osm_link}) | [Google Maps]({g_link})"

            for i, (nest_id, name, lat, lon, poly_path, poly_type) in enumerate(nests, start=1):
                poly_path = json.loads(poly_path)
                poly_type = "way" if poly_path == 0 else "relation"
                osm_link = f"https://www.openstreetmap.org/{poly_type}/{nest_id}"
                g_link = f"https://www.google.com/maps?q={lat},{lon}"
                description = get_desc(name, lat, lon, osm_link, g_link)

                if len(config.static_url) > 0:     
                    lats = []
                    lons = []
                    for poly in poly_path:
                        lats += [lat for lat, lon in poly]
                        lons += [lon for lat, lon in poly]
                    maxlat = max(lats)
                    minlat = min(lats)
                    maxlon = max(lons)
                    minlon = min(lons)
                    center_lat = minlat + ((maxlat - minlat) / 2)
                    center_lon = minlon + ((maxlon - minlon) / 2)
                    zoom = get_zoom(
                        [maxlat, maxlon],
                        [minlat, minlon],
                        1000,
                        600,
                        256
                    )
                    static_map_data = {
                        "style": "osm-bright",
                        "latitude": center_lat,
                        "longitude": center_lon,
                        "zoom": zoom,
                        "width": 1000,
                        "height": 600,
                        "scale": 1,
                        "polygons": []
                    }
                    for polygon in poly_path:
                        static_map_data["polygons"].append({
                            "fill_color": "rgba(48,227,116,0.4)",
                            "stroke_color": "rgba(15,166,128,0.9)",
                            "stroke_width": 2,
                            "path": polygon
                        })
                    #print(json.dumps(static_map_data,indent=4))

                    result = requests.post(config.static_url + "staticmap?pregenerate=true", json=static_map_data)
                    if "error" in result.text:
                        print(f"Error while generating Static Map:\n\n{static_map_data}\n{result.text}\n")
                        static_map_data["polygons"] = []
                        result = requests.post(config.static_url + "staticmap?pregenerate=true", json=static_map_data)
                    static_map = config.static_url + f"staticmap/pregenerated/{result.text}"
                    requests.get(static_map)
                else:
                    static_map = ""
                
                embed = discord.Embed(description=description)
                embed.set_image(url=static_map)
                embed.set_footer(text=f"Page {i}/{len(nests)}")
                await message.edit(embed=embed)

                def m_check(m):
                    return m.author.id == admin.id and channel == m.channel
                def check(reaction, user):
                    return str(reaction.emoji) in controls.keys() and user.id == admin.id
                while True:
                    try:
                        reaction, _ = await bot.wait_for("reaction_add", check=check, timeout=60*60*24)
                    except:
                        print("Error while trying to check a reaction")
                    else:     
                        control = controls[str(reaction.emoji)]
                        if control == "name":
                            m = await bot.wait_for("message", check=m_check)
                            name = m.content
                            area_data[str(nest_id)]["name"] = name
                            await m.delete()
                            await message.remove_reaction(reaction, admin)
                            embed.description = get_desc(name, lat, lon, osm_link, g_link)
                            embed.set_footer(text=f"Page {i}/{len(nests)}")
                            await message.edit(embed=embed)

                            with open(file_name, "w") as f:
                                f.write(json.dumps(area_data, indent=4))
                        elif control == "point":
                            m = await bot.wait_for("message", check=m_check)
                            point_str = m.content
                            points = point_str.split(",")
                            points = [float(p.strip()) for p in points]
                            area_data[str(nest_id)]["center"] = points
                            await m.delete()
                            await message.remove_reaction(reaction, admin)
                            embed.description = get_desc(name, points[0], points[1], osm_link, g_link)
                            embed.set_footer(text=f"Page {i}/{len(nests)}")
                            await message.edit(embed=embed)

                            with open(file_name, "w") as f:
                                f.write(json.dumps(area_data, indent=4))
                        elif control == "skip":
                            await message.remove_reaction(reaction, admin)
                            break
                        elif control == "exit":
                            await message.delete()
                            await bot.logout()
                            sys.exit()

            await bot.logout()

    bot.run(config.discord_token)

elif wanted == "2":
    migrates = {
        "1": "Migrate data from v1 (PMSFnestScript) to v2 (Nest Watcher)",
        "2": "Update area_data from csv to json (legacy, for beta testers)"
    }
    wanted2 = list_options(migrates)
    if wanted2 == "2":
        direc = "data/area_data/"
        for area_file_name in os.listdir(direc):
            if not area_file_name.endswith(".csv"):
                continue
            area_file_data = {}
            area_file_name = direc + area_file_name
            with open(area_file_name, mode="r", encoding="utf-8") as area_file:
                dict_reader = csv.DictReader(
                    area_file,
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                for line in dict_reader:
                    connect = []
                    for l in line.get("connect", "").split(";"):
                        if not l in ["0", ""]:
                            connect.append(int(l))
                    area_file_data[line["osm_id"]] = {
                        "name": line["name"],
                        "center": [float(line["center_lat"]), float(line["center_lon"])],
                        "connect": connect
                    }
                with open(area_file_name.replace(".csv", ".json"), "w+") as f:
                    f.write(json.dumps(area_file_data, indent=4))
        print("Done!")
    elif wanted2 == "1":
        print("This tool will copy your old default.ini values to the new format and convert the area data format.\nAttention: This WILL overwrite your current config with the options you set in PMSFnestScript")
        confirm = ""
        while confirm not in ["y", "n"]:
            confirm = input("Do you want to continue? (y/n) ").lower()
        if confirm == "n":
            sys.exit()

        print("Now write the whole path to your old PMSFnestScript (e.g. /root/PMSFnestScript/)")
        path = input()

        old_config = ConfigParser()
        old_config.read(path + "default.ini")

        new_config = ConfigParser()
        new_config.read("config/config.ini")

        new_config["Config"]["pokestop_pokemon"] = old_config.get("Nest Config", "POKESTOP_POKEMON")

        new_config["Scanner DB"]["scanner"] = old_config.get("DB Read", "SCANNER_SCHEMA")
        new_config["Scanner DB"]["name"] = old_config.get("DB Read", "NAME")
        new_config["Scanner DB"]["password"] = old_config.get("DB Read", "PASSWORD")
        new_config["Scanner DB"]["user"] = old_config.get("DB Read", "USER")
        new_config["Scanner DB"]["host"] = old_config.get("DB Read", "HOST")
        new_config["Scanner DB"]["port"] = old_config.get("DB Read", "PORT")

        new_config["Nest DB"]["name"] = old_config.get("DB Write", "NAME")
        new_config["Nest DB"]["password"] = old_config.get("DB Write", "PASSWORD")
        new_config["Nest DB"]["user"] = old_config.get("DB Write", "USER")
        new_config["Nest DB"]["host"] = old_config.get("DB Write", "HOST")
        new_config["Nest DB"]["port"] = old_config.get("DB Write", "PORT")

        new_config["Geojson"]["path"] = old_config.get("Geojson", "SAVE_PATH")
        new_config["Geojson"]["default_park_name"] = old_config.get("Geojson", "DEFAULT_PARK_NAME")
        new_config["Geojson"]["stroke"] = old_config.get("Geojson", "STROKE")
        new_config["Geojson"]["stroke_width"] = old_config.get("Geojson", "STROKE-WIDTH")
        new_config["Geojson"]["stroke_opacity"] = old_config.get("Geojson", "STROKE-OPACITY")
        new_config["Geojson"]["fill"] = old_config.get("Geojson", "FILL")
        new_config["Geojson"]["fill_opacity"] = old_config.get("Geojson", "FILL-OPACITY")

        new_config["Discord"]["language"] = old_config.get("Discord", "LANGUAGE")

        with open("config/config.ini", "w+") as configfile:
            new_config.write(configfile)

        path += "area_data/"

        for area_file_name in os.listdir(path):
            if not area_file_name.endswith(".csv"):
                continue
            area_file_data = {}
            with open(path + area_file_name, mode="r", encoding="utf-8") as area_file:
                dict_reader = csv.DictReader(
                    area_file,
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL,
                )
                for line in dict_reader:
                    connect = []
                    area_file_data[line["osm_id"]] = {
                        "name": line["name"],
                        "center": [float(line["center_lon"]), float(line["center_lat"])],
                        "connect": []
                    }
                with open("data/area_data/" + area_file_name.replace(".csv", ".json"), "w+") as f:
                    f.write(json.dumps(area_file_data, indent=4))
        
        print("Done. Go check if everything worked in config/config.ini and data/area_data")


elif wanted == "3":
    areaname = input("Area: ")
    with open("config/areas.json", "r") as f:
        areas = json.load(f)
        area = Area([a for a in areas if a["name"] == areaname][0], None)

    file_name = f"data/area_data/{areaname}.json"
    with open(file_name, "r") as f:
        area_data = json.load(f)


    print("Fetching data now. This may take a while")
    queries = Queries(config)
    queries.nest_cursor.execute(f"select name, nest_id, polygon_type from nests WHERE ST_CONTAINS(ST_GEOMFROMTEXT('POLYGON({area.sql_fence})'), point(lat, lon)) order by pokemon_avg desc;")
    nests = queries.nest_cursor.fetchall()

    query = ""
    for name, nestid, nesttype in nests:
        way = "way" if nesttype == 0 else "rel"
        query += f"{way}({nestid});"
    
    data = f"[out:json];({query});out body;>;out skel qt;"
    r = requests.post("http://overpass-api.de/api/interpreter", data=data)

    names = {}
    elements = r.json()["elements"]
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name", tags.get("official_name", None))
        if name is not None:
            names[element["id"]] = name

    for name, nestid, nesttype in nests:
        new_name = names.get(nestid, None)
        if new_name is None:
            continue
        if new_name == name:
            continue
    
        print(f"[{nestid}] {name} -> {new_name}")
        confirm = ""
        while confirm.lower() not in ("y", "n"):
            confirm = input("y/n ")
        
        if confirm.lower() == "y":
            try:
                area_data[str(nestid)]["name"] = name
                with open(file_name, "w") as f:
                    f.write(json.dumps(area_data, indent=4))
            except Exception as e:
                print(f"Got error {e}")
        else:
            continue

elif wanted == "4":
    print("This will delete all Servers the bot created to host emotes on. Continue?")
    confirm = ""
    while confirm.lower() not in ("y", "n"):
        confirm = input("[y/n] ")
    if confirm == "n":
        sys.exit()

    with open("data/emotes.json", "r") as f:
        emotes = json.load(f) 

    bot = discord.Client()
    @bot.event
    async def on_message(message):
        for server_id in emotes.keys():
            server = await bot.fetch_guild(server_id)
            await server.delete()
        await bot.logout()

    bot.run(config.discord_token)

    with open("data/emotes.json", "w") as f:
        f.write("{}")

    print("Done. Now re-run the analyzer to regenerate emotes")

elif wanted == "5":
    from nestwatcher.overpass import get_osm_data
    from nestwatcher.analyze import osm_date
    print("starting now")
    with open("config/areas.json", "r") as area_file:
        raw_areas = json.load(area_file)
    for area in raw_areas:
        area = Area(area)
        file_name = f"data/osm_data/{area.name} {osm_date().replace(':', '')}.json"
        nest_json = get_osm_data(area.bbox, osm_date(), file_name)
    print("All done")