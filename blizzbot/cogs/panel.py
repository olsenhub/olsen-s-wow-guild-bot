import discord
from discord import app_commands
from discord.ext import commands

from blizzbot.cogs.active_players import build_active_embed
from blizzbot.cogs.character_lookup import build_character_embed
from blizzbot.cogs.leaderboards import LeaderboardView, build_leaderboard_embed


class CharacterLookupModal(discord.ui.Modal, title="Character Lookup"):
    name = discord.ui.TextInput(label="Character name", placeholder="e.g. Thrallnaught")

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = await build_character_embed(self.bot, str(self.name.value))
        await interaction.followup.send(embed=embed, ephemeral=True)


class PanelView(discord.ui.View):
    """Persistent view (timeout=None, static custom_ids) — registered once in on_ready
    so the buttons keep working across bot restarts."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Leaderboards", style=discord.ButtonStyle.primary, custom_id="panel_leaderboards", emoji="🏆")
    async def leaderboards(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = LeaderboardView(self.bot.db_conn)
        embed = build_leaderboard_embed(self.bot.db_conn, view.metric, view.character_class)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Active Players", style=discord.ButtonStyle.success, custom_id="panel_active", emoji="🟢")
    async def active_players(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=build_active_embed(self.bot), ephemeral=True)

    @discord.ui.button(label="Character Lookup", style=discord.ButtonStyle.secondary, custom_id="panel_lookup", emoji="🔍")
    async def character_lookup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CharacterLookupModal(self.bot))


class Panel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="panel", description="Open the guild tools panel")
    async def panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚔️ Guild Tools",
            description="Pick an option below.",
            color=discord.Color.dark_purple(),
        )
        await interaction.response.send_message(embed=embed, view=PanelView(self.bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(Panel(bot))
