from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db
from blizzbot.api import BattleNetError
from blizzbot.character_sheet import build_character_sheet
from blizzbot.emojis import class_emoji


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
    race = profile.get("race", {}).get("name", "")
    char_class = profile.get("character_class", {}).get("name", "?")
    char_class_id = profile.get("character_class", {}).get("id")
    spec = (profile.get("active_spec") or {}).get("name")
    item_level = profile.get("average_item_level")
    achievement_points = profile.get("achievement_points", 0)
    guild_name = (profile.get("guild") or {}).get("name")
    faction = (profile.get("faction") or {}).get("type")
    last_login_ms = profile.get("last_login_timestamp")
    last_login = (
        datetime.fromtimestamp(last_login_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
        if last_login_ms else "unknown"
    )

    emoji = class_emoji(bot, char_class)

    embed = discord.Embed(
        title=f"{emoji} {name} — Level {level} {char_class}" + (f" ({spec})" if spec else ""),
        color=discord.Color.blurple(),
    )
    if exact_cached is not None and exact_cached["guild_rank"] is not None:
        embed.add_field(name="Guild Rank", value=f"#{exact_cached['guild_rank']}", inline=True)
    embed.add_field(name="Last Login", value=last_login, inline=True)

    sheet_file = None
    try:
        equipment = await bot.bnet_client.character_equipment(realm_slug, character_name)
        media = await bot.bnet_client.character_media(realm_slug, character_name)
        assets = media.get("assets", [])
        render_url = next((a["value"] for a in assets if a.get("key") in ("main-raw", "main")), None)
        class_icon_url = (
            await bot.bnet_client.playable_class_icon_url(char_class_id) if char_class_id else None
        )
        try:
            specializations = await bot.bnet_client.character_specializations(realm_slug, character_name)
        except BattleNetError:
            specializations = None  # sheet still renders, just without the talent panel
        sheet_buf = await build_character_sheet(
            bot.bnet_client,
            name=name, level=level, race=race, char_class=char_class, spec=spec,
            guild_name=guild_name, item_level=item_level, achievement_points=achievement_points,
            faction=faction, equipment=equipment, render_url=render_url, class_icon_url=class_icon_url,
            specializations=specializations,
        )
        sheet_file = discord.File(sheet_buf, filename="character.png")
        embed.set_image(url="attachment://character.png")
    except BattleNetError:
        pass

    return embed, sheet_file


class CharacterLookup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="character", description="Look up a guild member's full profile")
    @app_commands.describe(name="Character name")
    async def character(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        embed, sheet_file = await build_character_embed(self.bot, name)
        kwargs = {"file": sheet_file} if sheet_file else {}
        await interaction.followup.send(embed=embed, ephemeral=True, **kwargs)

    @character.autocomplete("name")
    async def character_autocomplete(self, interaction: discord.Interaction, current: str):
        rows = db.search_member_names(self.bot.db_conn, current, limit=25)
        return [app_commands.Choice(name=row["character_name"], value=row["character_name"]) for row in rows]


async def setup(bot: commands.Bot):
    await bot.add_cog(CharacterLookup(bot))
