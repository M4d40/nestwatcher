import os
import discord
import csv
import json

from utils.config import Config

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
    channel_id = int(input())
    print("Starting the bot now. Please head over to the channel and follow your bot's instructions.")

    bot = discord.Client()
    @bot.event
    async def on_ready():
        directory = os.fsencode("area_data/")
        channel = await bot.fetch_channel(channel_id)
        for file in os.listdir(directory):
            filename = os.fsdecode(file)
            if filename.endswith("csv"):
                area_file_data = []
                with open("area_data/"+filename, "r") as area_file:
                    dict_reader = csv.DictReader(
                        area_file,
                        quotechar='"',
                        quoting=csv.QUOTE_MINIMAL,
                    )
                    for line in dict_reader:
                        area_file_data.append([
                            int(line["osm_id"]),
                            line["name"],
                            line["center_lat"],
                            line["center_lon"]
                        ])
                for osm_id, name, lat, lon in area_file_data:
                    await channel.send(f"{osm_id}, {name}")
                    def check(m):
                        return (m.channel == channel and m.author != bot.user)
                    new_name = await bot.wait_for('message', check=check).content
                    if new_name.lower() == "skip":
                        continue
                    
                    

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