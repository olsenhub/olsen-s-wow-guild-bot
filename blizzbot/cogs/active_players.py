from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db


def _relative_time(timestamp_ms: int | None) -> str:
    if not timestamp_ms:
        return "unknown"
    last_login = datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)
    delta = datetime.now(UTC) - last_login
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return "less than an hour ago"
    if hours < 24:
        return f"{int(hours)}h ago"
    return f"{int(hours // 24)}d ago"


def build_active_embed(bot: commands.Bot) -> discord.Embed:
    conn = bot.db_conn
    rows = db.recently_active(conn)
    links_by_character = {
        (link["character_name"], link["realm_slug"]): link["discord_user_id"]
        for link in db.all_links(conn)
    }

    guild = bot.guilds[0] if bot.guilds else None

    lines = []
    for row in rows:
        key = (row["character_name"], row["realm_slug"])
        discord_user_id = links_by_character.get(key)
        online_badge = ""
        if discord_user_id and guild:
            member = guild.get_member(discord_user_id)
            if member and member.status in (discord.Status.online, discord.Status.idle, discord.Status.dnd):
                online_badge = " 🟢 online on Discord"
        lines.append(
            f"**{row['character_name']}** ({row['character_class']}, lvl {row['level']}) — "
            f"last seen {_relative_time(row['last_login_timestamp'])}{online_badge}"
        )

    embed = discord.Embed(
        title="🟢 Recently Active",
        description="\n".join(lines) if lines else "No data yet — the poller hasn't synced anyone.",
        color=discord.Color.green(),
    )
    embed.set_footer(
        text="'last seen' is login time only (Blizzard's API has no live location or logout signal). "
        "🟢 means they've linked their character with /link and are currently online on Discord."
    )
    return embed


class ActivePlayers(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="active", description="Show recently active guild members")
    async def active(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=build_active_embed(self.bot), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ActivePlayers(bot))
