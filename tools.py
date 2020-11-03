import os
import discord
import csv
import json
import sys
import requests

from utils.config import Config
from utils.area import get_zoom
from utils.queries import Queries

tools = {
    "1": "Update area_data using Discord",
    "2": "Migrate data to a newer version"
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
    print("The Discord Bot configured in config/config.ini will now ask you to name every park saved in area_data/.\nPlease type the Channel ID you want to do that in.\nThe bot will not check for permissions, so make sure the channel can only be accessed by you and the bot.")
    areaname = input("Area: ")
    print("Starting the bot now. Please head over to the channel and follow your bot's instructions.")

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

            queries.nest_cursor.execute("select nest_id, name, lat, lon, polygon_path, polygon_type from nests order by pokemon_avg desc")
            nests = queries.nest_cursor.fetchall()

            file_name = f"data/area_data/{areaname}.json"
            with open(file_name, "r") as f:
                area_data = json.load(f)

            def get_desc(name, lat, lon, osm_link, g_link):
                return f"Name: **{name}**\nCenter: `{round(lat, 5)},{round(lon, 6)}`\n\n[OSM Link]({osm_link}) | [Google Maps]({g_link})"

            for nest_id, name, lat, lon, poly_path, poly_type in nests:
                poly_path = json.loads(poly_path)
                poly_type = "way" if poly_path == 0 else "relation"
                osm_link = f"https://www.openstreetmap.org/{poly_type}/{nest_id}"
                g_link = f"https://www.google.com/maps?q={lat},{lon}"
                description = get_desc(name, lat, lon, osm_link, g_link)
                
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
                static_map = config.static_url + f"staticmap/pregenerated/{result.text}"
                requests.get(static_map)
                
                embed = discord.Embed(description=description)
                embed.set_image(url=static_map)
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
                            await message.edit(embed=embed)

                            with open(file_name, "w") as f:
                                f.write(json.dumps(area_data, indent=4))
                        elif control == "point":
                            print("")
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
        "1": "Migrate data from v1 to v2 (not yet working)",
        "2": "Update area_data from csv to json"
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