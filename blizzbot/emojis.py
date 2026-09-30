"""Class/slot emoji helpers. Prefers a matching custom emoji already uploaded --
application emojis (Developer Portal -> Emojis, works across every server the bot
is in) take priority, then the current guild's own emojis -- falling back to a
plain Unicode icon otherwise."""

import logging

import discord
import httpx
from discord.ext import commands

from blizzbot import db

log = logging.getLogger("emojis")

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


def _spec_emoji_name(class_name: str, spec_name: str) -> str:
    """Spec names collide across classes (Holy, Protection, Restoration, Frost...),
    so the class is part of the emoji name. Discord allows [A-Za-z0-9_], 2-32 chars."""
    def clean(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())
    return f"spec_{clean(class_name)}_{clean(spec_name)}"


def spec_emoji(bot: commands.Bot, class_name: str | None, spec_name: str | None) -> str:
    """The uploaded spec icon (see sync_spec_emojis), or "" if it isn't there yet."""
    if not class_name or not spec_name:
        return ""
    name = _spec_emoji_name(class_name, spec_name)
    found = discord.utils.find(lambda e: e.name == name, getattr(bot, "application_emojis", []))
    return str(found) if found else ""


async def sync_spec_emojis(bot: commands.Bot) -> None:
    """Uploads an application emoji for every spec seen on the roster that doesn't have
    one yet. Icons come from Battle.net's playable-specialization media. Runs on a timer
    because the poller is what discovers specs, and it can only have run after the bot
    started; a failure on one spec just skips it until the next run."""
    existing = {e.name for e in getattr(bot, "application_emojis", [])}
    missing = [
        row for row in db.known_specs(bot.db_conn)
        if _spec_emoji_name(row["character_class"], row["active_spec"]) not in existing
    ]
    if not missing:
        return
    log.info("Uploading %d spec emoji(s)", len(missing))
    async with httpx.AsyncClient(timeout=10.0) as http:
        for row in missing:
            name = _spec_emoji_name(row["character_class"], row["active_spec"])
            try:
                url = await bot.bnet_client.playable_specialization_icon_url(row["active_spec_id"])
                resp = await http.get(url) if url else None
                if resp is None or resp.status_code != 200:
                    log.warning("No icon for %s", name)
                    continue
                emoji = await bot.create_application_emoji(name=name, image=resp.content)
                bot.application_emojis.append(emoji)
            except Exception:
                log.exception("Could not create spec emoji %s", name)
