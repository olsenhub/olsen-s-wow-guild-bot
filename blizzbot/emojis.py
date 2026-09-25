"""Class/slot emoji helpers. Prefers a matching custom emoji already uploaded to the
guild (common on WoW Discord servers -- e.g. an emoji literally named "rogue" or
"classicon_rogue"), falls back to a plain Unicode icon otherwise."""

import discord

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


def class_emoji(guild: discord.Guild | None, class_name: str | None) -> str:
    """Returns a custom `<:name:id>` emoji if the guild has a matching one uploaded
    (tries "rogue", "classicon_rogue", "wow_rogue" style names), else a Unicode fallback."""
    if not class_name:
        return ""
    if guild:
        target = _normalize(class_name)
        candidates = {target, f"class{target}", f"classicon{target}", f"wow{target}"}
        found = discord.utils.find(lambda e: _normalize(e.name) in candidates, guild.emojis)
        if found:
            return str(found)
    return CLASS_FALLBACK_EMOJI.get(class_name, "")
