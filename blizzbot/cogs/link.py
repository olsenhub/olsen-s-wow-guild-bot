import discord
from discord import app_commands
from discord.ext import commands

from blizzbot import db


def is_officer(interaction: discord.Interaction) -> bool:
    officer_role_id = interaction.client.config.officer_role_id
    if not officer_role_id or not isinstance(interaction.user, discord.Member):
        return False
    return any(role.id == officer_role_id for role in interaction.user.roles)


class Link(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="link", description="Link your Discord account to your WoW character")
    @app_commands.describe(character_name="Your character's name")
    async def link(self, interaction: discord.Interaction, character_name: str):
        conn = self.bot.db_conn
        matches = db.search_member_names(conn, character_name, limit=1)
        if not matches or matches[0]["character_name"].lower() != character_name.lower():
            await interaction.response.send_message(
                f"Couldn't find **{character_name}** in the guild roster.", ephemeral=True
            )
            return
        realm_slug = matches[0]["realm_slug"]
        exact_name = matches[0]["character_name"]

        ok = db.link_character(conn, interaction.user.id, exact_name, realm_slug)
        if ok:
            await interaction.response.send_message(
                f"Linked you to **{exact_name}**. Use `/unlink` to remove it, or ask an officer "
                "to `/forceunlink` if this was claimed by mistake.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"**{exact_name}** is already linked to someone else. "
                "If that's wrong, ask an officer to `/forceunlink` it.",
                ephemeral=True,
            )

    @app_commands.command(name="unlink", description="Remove your character link")
    async def unlink(self, interaction: discord.Interaction):
        removed = db.unlink_own(self.bot.db_conn, interaction.user.id)
        msg = "Your link has been removed." if removed else "You don't have a link set."
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="forceunlink", description="[Officer] Remove any character's link")
    @app_commands.describe(character_name="Character name to unlink")
    async def forceunlink(self, interaction: discord.Interaction, character_name: str):
        if not is_officer(interaction):
            await interaction.response.send_message("Officers only.", ephemeral=True)
            return
        conn = self.bot.db_conn
        matches = db.search_member_names(conn, character_name, limit=1)
        realm_slug = matches[0]["realm_slug"] if matches else self.bot.config.wow_realm_slug
        removed = db.force_unlink(conn, character_name, realm_slug)
        msg = f"Removed link for **{character_name}**." if removed else f"No link found for **{character_name}**."
        await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Link(bot))
