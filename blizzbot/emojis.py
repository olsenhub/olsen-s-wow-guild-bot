"""Class/slot emoji helpers. Prefers a matching custom emoji already uploaded --
application emojis (Developer Portal -> Emojis, works across every server the bot
is in) take priority, then the current guild's own emojis -- falling back to a
plain Unicode icon otherwise."""

import discord
from discord.ext import commands

CLASS_FALLBACK_EMOJI = {
    "Warrior": "⚔️",
    "Paladin": "🛡️",
    "Hunter": "🏹",
    "Rogue": "🗡️",
    "Priest": "✨",
    "Death Knight": "💀",
    "Shaman": "🌊",
    "Mage": "🔥",
    "Warlock": "👹",
    "Monk": "🥋",
    "Druid": "🐾",
}


def _normalize(name: str) -> str:
    return name.lower().replace(" ", "").replace("'", "").replace("-", "")


def class_emoji(bot: commands.Bot, class_name: str | None) -> str:
    """Returns a custom `<:name:id>` emoji if a matching one is uploaded (tries
    "rogue", "classicon_rogue", "wow_rogue" style names), else a Unicode fallback."""
    if not class_name:
        return ""

    target = _normalize(class_name)
    candidates = {target, f"class{target}", f"classicon{target}", f"wow{target}"}

    app_emojis = getattr(bot, "application_emojis", [])
    found = discord.utils.find(lambda e: _normalize(e.name) in candidates, app_emojis)
    if found:
        return str(found)

    guild = bot.guilds[0] if bot.guilds else None
    if guild:
        found = discord.utils.find(lambda e: _normalize(e.name) in candidates, guild.emojis)
        if found:
            return str(found)

    return CLASS_FALLBACK_EMOJI.get(class_name, "")
