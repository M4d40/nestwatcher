import discord
import requests
import json

from nestwatcher.logging import log

async def get_emotes(bot, nesting_mons, config):
    try:
        with open("data/emotes.json", "r") as f:
            emote_servers = json.load(f)
    except (IOError, OSError):
        emote_servers = {}
        log.info("This seems to be your first run. Your bot will now create 1 server and fill it with emotes, so prepare for some wait time.")
    emotes = {}
    final_emotes = {}
    for server, data in emote_servers.items():
        for monid, emoteid in data.items():
            final_emotes[int(monid)] = int(emoteid)
            emotes[monid] = {
                "emote_id": int(emoteid),
                "server_id": int(server)
            }
    log.info("Comparing your bot's emotes to needed nesting mons.")
    for monid in nesting_mons:
        if monid in emotes.keys():
            emotes.pop(monid)
            continue
        free_emotes = False
        for guild_id in emote_servers.keys():
            guild = await bot.fetch_guild(guild_id)
            if len(guild.emojis) < 50:
                free_emotes = True
                emote_servers[guild.id] = {}
                break
        if not free_emotes:
            for guild in bot.guilds:
                if guild.name == "Nest Emotes":
                    if len(guild.emojis) < 50:
                        free_emotes = True
                        emote_servers[guild.id] = {}
                        break
        if not free_emotes:
            guild = await bot.create_guild("Nest Emotes")
            channel = await guild.create_text_channel("hello")
            invite = await channel.create_invite()
            emote_servers[guild.id] = {}
            log.info(f"Created Emote Server. Invite code: {invite.code}")

        emote_name = "m" + monid
        image_url = config.icon_repo + f"pokemon_icon_{monid.zfill(3)}_00.png"
        image = requests.get(image_url).content

        emote = await guild.create_custom_emoji(name=emote_name, image=image)
        emote_servers[guild.id][monid] = emote.id
        final_emotes[int(monid)] = emote.id

    for monid, data in emotes.items():
        guild = await bot.fetch_guild(data["server_id"])
        emote = await guild.fetch_emoji(data["emote_id"])
        await emote.delete()

    with open("data/emotes.json", "w+") as f:
        f.write(json.dumps(emote_servers, indent=4))   
    return final_emotes