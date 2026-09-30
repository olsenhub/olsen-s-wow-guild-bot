import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db
from blizzbot.emojis import class_emoji, spec_emoji

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


def _name_cell(bot, row, show_spec_text: bool) -> str:
    """class icon, spec icon, name. Until a spec's icon has been uploaded (the bot does
    that a few minutes after the poller first sees it) fall back to the spec's name."""
    icon = spec_emoji(bot, row["character_class"], row["active_spec"])
    cell = f"{class_emoji(bot, row['character_class'])} " + (f"{icon} " if icon else "") + row["character_name"]
    if not icon and row["active_spec"] and show_spec_text:
        cell += f" *({row['active_spec']})*"
    return cell


def build_leaderboard_embed(conn, metric: str, character_class: str | None,
                             bot: commands.Bot | None = None, active_spec: str | None = None) -> discord.Embed:
    rows = db.leaderboard(conn, metric, character_class, active_spec)
    scope = " — ".join(filter(None, [character_class, active_spec])) or "Overall"
    embed = discord.Embed(
        title=f"🏆 Leaderboard — {METRICS[metric]} ({scope})",
        color=discord.Color.gold(),
    )
    if not rows:
        embed.description = "No data yet — the poller hasn't synced anyone matching this filter."
        return embed

    ranks = [f"#{i}" for i in range(1, len(rows) + 1)]
    names = [_name_cell(bot, row, show_spec_text=not active_spec) for row in rows]
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
        view.active_spec = None  # a spec only makes sense within its class
        await view.refresh(interaction)


class SpecSelect(discord.ui.Select):
    """Spec options come from the specs actually seen in the DB for the chosen class,
    so there's no hardcoded spec list to keep in sync with the game."""

    def __init__(self, specs: list[str], selected: str | None = None):
        if specs:
            options = [discord.SelectOption(label="Any spec", value="__all__", default=selected is None)] + [
                discord.SelectOption(label=spec, value=spec, default=(spec == selected)) for spec in specs
            ]
        else:
            options = [discord.SelectOption(label="Pick a class to filter by spec", value="__all__")]
        super().__init__(placeholder="Spec...", options=options, custom_id="lb_spec", disabled=not specs)

    async def callback(self, interaction: discord.Interaction):
        view: LeaderboardView = self.view
        view.active_spec = None if self.values[0] == "__all__" else self.values[0]
        await view.refresh(interaction)


class LeaderboardView(discord.ui.View):
    def __init__(self, conn, bot: commands.Bot | None = None):
        super().__init__(timeout=180)
        self.conn = conn
        self.bot = bot
        self.metric = DEFAULT_METRIC
        self.character_class: str | None = None
        self.active_spec: str | None = None
        self.metric_select = MetricSelect(self.metric)
        self.class_select = ClassSelect()
        self.spec_select = SpecSelect([])
        self.add_item(self.metric_select)
        self.add_item(self.class_select)
        self.add_item(self.spec_select)

    def _sync_selects(self) -> None:
        # Discord re-renders from the view's own state on every edit, so the selects
        # have to be told what's currently chosen or they snap back to their first option.
        for option in self.metric_select.options:
            option.default = option.value == self.metric
        for option in self.class_select.options:
            option.default = option.value == (self.character_class or "__all__")
        self.remove_item(self.spec_select)
        specs = db.specs_for_class(self.conn, self.character_class) if self.character_class else []
        self.spec_select = SpecSelect(specs, self.active_spec)
        self.add_item(self.spec_select)

    async def refresh(self, interaction: discord.Interaction):
        self._sync_selects()
        embed = build_leaderboard_embed(self.conn, self.metric, self.character_class, self.bot, self.active_spec)
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
