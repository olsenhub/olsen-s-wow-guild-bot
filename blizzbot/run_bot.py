import logging

import discord
from discord.ext import commands

from blizzbot import db
from blizzbot.api import BattleNetClient
from blizzbot.config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

COGS = [
    "blizzbot.cogs.leaderboards",
    "blizzbot.cogs.active_players",
    "blizzbot.cogs.character_lookup",
    "blizzbot.cogs.link",
    "blizzbot.cogs.auction_house",
    "blizzbot.cogs.panel",
]


class BlizzBot(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.members = True
        intents.presences = True
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.db_conn = db.connect(config.database_path)
        self.bnet_client = BattleNetClient(config)

    async def setup_hook(self):
        for cog in COGS:
            await self.load_extension(cog)

        # Register the persistent panel view so its buttons survive restarts.
        from blizzbot.cogs.panel import PanelView
        self.add_view(PanelView(self))

        try:
            self.application_emojis = await self.fetch_application_emojis()
            log.info("Loaded %d application emoji(s)", len(self.application_emojis))
        except discord.HTTPException:
            self.application_emojis = []
            log.exception("Could not fetch application emojis")

        if self.config.discord_guild_id:
            guild_obj = discord.Object(id=self.config.discord_guild_id)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            log.info("Synced commands to guild %s", self.config.discord_guild_id)
        else:
            await self.tree.sync()
            log.info("Synced commands globally (can take up to an hour to propagate)")

    async def close(self):
        await self.bnet_client.aclose()
        self.db_conn.close()
        await super().close()


def main() -> None:
    config = load_config()
    if not config.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")
    bot = BlizzBot(config)

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (%s)", bot.user, bot.user.id)

    bot.run(config.discord_bot_token)


if __name__ == "__main__":
    main()
