import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db
from blizzbot.emojis import class_emoji

METRICS = {
    "level": "Level",
    "achievement_points": "Achievement Points",
    "item_level": "Item Level",
}

WOW_CLASSES = [
    "Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Death Knight",
    "Shaman", "Mage", "Warlock", "Monk", "Druid",
]


def build_leaderboard_embed(conn, metric: str, character_class: str | None,
                             guild: discord.Guild | None = None) -> discord.Embed:
    rows = db.leaderboard(conn, metric, character_class)
    scope = character_class or "Overall"
    embed = discord.Embed(
        title=f"🏆 Leaderboard — {METRICS[metric]} ({scope})",
        color=discord.Color.gold(),
    )
    if not rows:
        embed.description = "No data yet — the poller hasn't synced anyone matching this filter."
        return embed
    lines = [
        f"**{i}.** {class_emoji(guild, row['character_class'])} {row['character_name']} — {row['value']}"
        for i, row in enumerate(rows, start=1)
    ]
    embed.description = "\n".join(lines)
    return embed


class MetricSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=label, value=key) for key, label in METRICS.items()]
        super().__init__(placeholder="Metric...", options=options, custom_id="lb_metric")

    async def callback(self, interaction: discord.Interaction):
        view: LeaderboardView = self.view
        view.metric = self.values[0]
        await view.refresh(interaction)


class ClassSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label="Overall", value="__all__")] + [
            discord.SelectOption(label=c, value=c) for c in WOW_CLASSES
        ]
        super().__init__(placeholder="Class...", options=options, custom_id="lb_class")

    async def callback(self, interaction: discord.Interaction):
        view: LeaderboardView = self.view
        view.character_class = None if self.values[0] == "__all__" else self.values[0]
        await view.refresh(interaction)


class LeaderboardView(discord.ui.View):
    def __init__(self, conn, guild: discord.Guild | None = None):
        super().__init__(timeout=180)
        self.conn = conn
        self.guild = guild
        self.metric = "level"
        self.character_class: str | None = None
        self.add_item(MetricSelect())
        self.add_item(ClassSelect())

    async def refresh(self, interaction: discord.Interaction):
        embed = build_leaderboard_embed(self.conn, self.metric, self.character_class, self.guild)
        await interaction.response.edit_message(embed=embed, view=self)


class Leaderboards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show guild leaderboards")
    async def leaderboard(self, interaction: discord.Interaction):
        guild = self.bot.guilds[0] if self.bot.guilds else None
        view = LeaderboardView(self.bot.db_conn, guild)
        embed = build_leaderboard_embed(self.bot.db_conn, view.metric, view.character_class, guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboards(bot))
