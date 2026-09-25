import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db
from blizzbot.emojis import class_emoji

METRICS = {
    "achievement_points": "Achievement Points",
    "item_level": "Item Level",
    "level": "Level",
}
DEFAULT_METRIC = "achievement_points"

WOW_CLASSES = [
    "Warrior", "Paladin", "Hunter", "Rogue", "Priest", "Death Knight",
    "Shaman", "Mage", "Warlock", "Monk", "Druid",
]


def build_leaderboard_embed(conn, metric: str, character_class: str | None,
                             bot: commands.Bot | None = None) -> discord.Embed:
    rows = db.leaderboard(conn, metric, character_class)
    scope = character_class or "Overall"
    embed = discord.Embed(
        title=f"🏆 Leaderboard — {METRICS[metric]} ({scope})",
        color=discord.Color.gold(),
    )
    if not rows:
        embed.description = "No data yet — the poller hasn't synced anyone matching this filter."
        return embed

    ranks = [f"#{i}" for i in range(1, len(rows) + 1)]
    names = [f"{class_emoji(bot, row['character_class'])} {row['character_name']}" for row in rows]
    values = [str(row["value"]) for row in rows]

    embed.add_field(name="Rank", value="\n".join(ranks), inline=True)
    embed.add_field(name="Character", value="\n".join(names), inline=True)
    embed.add_field(name=METRICS[metric], value="\n".join(values), inline=True)
    return embed


class MetricSelect(discord.ui.Select):
    def __init__(self, selected: str = DEFAULT_METRIC):
        options = [
            discord.SelectOption(label=label, value=key, default=(key == selected))
            for key, label in METRICS.items()
        ]
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
    def __init__(self, conn, bot: commands.Bot | None = None):
        super().__init__(timeout=180)
        self.conn = conn
        self.bot = bot
        self.metric = DEFAULT_METRIC
        self.character_class: str | None = None
        self.add_item(MetricSelect(self.metric))
        self.add_item(ClassSelect())

    async def refresh(self, interaction: discord.Interaction):
        embed = build_leaderboard_embed(self.conn, self.metric, self.character_class, self.bot)
        await interaction.response.edit_message(embed=embed, view=self)


class Leaderboards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="leaderboard", description="Show guild leaderboards")
    async def leaderboard(self, interaction: discord.Interaction):
        view = LeaderboardView(self.bot.db_conn, self.bot)
        embed = build_leaderboard_embed(self.bot.db_conn, view.metric, view.character_class, self.bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboards(bot))
