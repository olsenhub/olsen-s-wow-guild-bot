from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db
from blizzbot.api import BattleNetError
from blizzbot.emojis import SLOT_EMOJI, class_emoji
from blizzbot.gear_image import GEAR_SLOT_ORDER, build_gear_image

QUALITY_DOT = {
    "POOR": "🔘",
    "COMMON": "⚪",
    "UNCOMMON": "🟢",
    "RARE": "🔵",
    "EPIC": "🟣",
    "LEGENDARY": "🟠",
}


def _format_gear_columns(equipment: dict) -> tuple[str, str]:
    by_slot = {i["slot"]["type"]: i for i in equipment.get("equipped_items", [])}
    lines = []
    for slot in GEAR_SLOT_ORDER:
        item = by_slot.get(slot)
        slot_icon = SLOT_EMOJI.get(slot, "▫️")
        if item:
            quality_dot = QUALITY_DOT.get(item.get("quality", {}).get("type"), "⚪")
            lines.append(f"{slot_icon} {quality_dot} {item['name']}")
        else:
            lines.append(f"{slot_icon} *(empty)*")
    mid = (len(lines) + 1) // 2
    return "\n".join(lines[:mid]) or "​", "\n".join(lines[mid:]) or "​"


async def build_character_embed(bot: commands.Bot, character_name: str) -> tuple[discord.Embed, discord.File | None]:
    conn = bot.db_conn
    cached = db.search_member_names(conn, character_name, limit=1)
    exact_cached = (
        db.get_member(conn, cached[0]["character_name"], cached[0]["realm_slug"])
        if cached and cached[0]["character_name"].lower() == character_name.lower()
        else None
    )
    realm_slug = cached[0]["realm_slug"] if cached else bot.config.wow_realm_slug

    try:
        profile = await bot.bnet_client.character_profile(realm_slug, character_name)
    except BattleNetError:
        return discord.Embed(
            title="Not found",
            description=f"Couldn't find **{character_name}** on `{realm_slug}` (or their profile is private).",
            color=discord.Color.red(),
        ), None

    name = profile.get("name", character_name)
    level = profile.get("level")
    char_class = profile.get("character_class", {}).get("name", "?")
    spec = (profile.get("active_spec") or {}).get("name")
    item_level = profile.get("average_item_level")
    achievement_points = profile.get("achievement_points", 0)
    guild_name = (profile.get("guild") or {}).get("name")
    last_login_ms = profile.get("last_login_timestamp")
    last_login = (
        datetime.fromtimestamp(last_login_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        if last_login_ms else "unknown"
    )

    guild = bot.guilds[0] if bot.guilds else None
    emoji = class_emoji(guild, char_class)

    embed = discord.Embed(
        title=f"{emoji} {name} — Level {level} {char_class}" + (f" ({spec})" if spec else ""),
        color=discord.Color.blurple(),
    )
    if guild_name:
        embed.add_field(name="Guild", value=guild_name, inline=True)
    embed.add_field(name="Item Level", value=str(item_level or "?"), inline=True)
    embed.add_field(name="Achievement Points", value=str(achievement_points), inline=True)
    if exact_cached is not None and exact_cached["guild_rank"] is not None:
        embed.add_field(name="Guild Rank", value=f"#{exact_cached['guild_rank']}", inline=True)
    embed.add_field(name="Last Login", value=last_login, inline=False)

    gear_file = None
    try:
        equipment = await bot.bnet_client.character_equipment(realm_slug, character_name)
        left, right = _format_gear_columns(equipment)
        embed.add_field(name="Gear", value=left, inline=True)
        embed.add_field(name="​", value=right, inline=True)
        embed.set_footer(text="⚪ Common  🟢 Uncommon  🔵 Rare  🟣 Epic  🟠 Legendary")

        image_buf = await build_gear_image(bot.bnet_client, equipment)
        if image_buf:
            gear_file = discord.File(image_buf, filename="gear.png")
            embed.set_image(url="attachment://gear.png")
    except BattleNetError:
        pass

    try:
        media = await bot.bnet_client.character_media(realm_slug, character_name)
        render = next(
            (a["value"] for a in media.get("assets", []) if a.get("key") in ("main-raw", "main")),
            None,
        )
        if render:
            embed.set_thumbnail(url=render)
    except BattleNetError:
        pass

    return embed, gear_file


class CharacterLookup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="character", description="Look up a guild member's full profile")
    @app_commands.describe(name="Character name")
    async def character(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        embed, gear_file = await build_character_embed(self.bot, name)
        kwargs = {"file": gear_file} if gear_file else {}
        await interaction.followup.send(embed=embed, ephemeral=True, **kwargs)

    @character.autocomplete("name")
    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = db.search_member_names(self.bot.db_conn, current, limit=25)
        return [app_commands.Choice(name=row["character_name"], value=row["character_name"]) for row in rows]


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterLookup(bot))
