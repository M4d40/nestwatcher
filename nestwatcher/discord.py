import discord
import requests
import json

from nestwatcher.logging import log

def existing_emotes(guilds, emote_name):
    for guild in guilds:
        for emoji in guild.emojis:
            if emoji.name == emote_name:
                return emoji.id
    return None

async def get_emotes(bot, nesting_mons, config):
    guilds = []
    for guild in bot.guilds:
        if guild.name == "Nest Emotes":
            guilds.append(guild)

    emote_names = [f"m{mid}" for mid in nesting_mons]
    # emote removing
    for guild in guilds:
        for emoji in guild.emojis:
            if emoji.name not in emote_names:
                log.info(f"Found emoji {emoji.name} not being used anymore - deleting")
                await emoji.delete()

    # emote creation
    final_emotes = {}
    for monid in nesting_mons:
        emote_name = f"m{monid}"
        existing = existing_emotes(guilds, emote_name)
        if existing:
            final_emotes[int(monid)] = existing
            continue

        free_guild = None
        for guild in guilds:
            if len(guild.emojis) < guild.emoji_limit:
                free_guild = guild

        if not free_guild:
            try:
                free_guild = await bot.create_guild(name="Nest Emotes")
                channel = await free_guild.create_text_channel("hello")
                invite = await channel.create_invite()
                log.info(f"Created new emote server. Invite code: {invite.code}") 
                guilds.append(free_guild)
            except Exception as e:
                log.error("Exception while trying to create a guild. Aborting")
                log.exception(e)
                return final_emotes

        image_url = config.icon_repo + f"pokemon/{monid}.png"
        image = requests.get(image_url).content
        emoji = await free_guild.create_custom_emoji(name=emote_name, image=image)
        log.info(f"Created emoji {emote_name}")

        final_emotes[int(monid)] = emoji.id

    return final_emotes
