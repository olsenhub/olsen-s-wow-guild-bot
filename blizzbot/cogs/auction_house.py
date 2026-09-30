"""Live Auction House price lookup. Blizzard's API only exposes a current
snapshot of active listings -- there's no price-history endpoint, so this
only ever shows "right now" prices. The full per-realm-cluster auction dump
(tens of thousands of listings) is cached in memory for a few minutes so
repeated /ah lookups don't refetch it every time."""

import time

import discord
from discord import app_commands
from discord.ext import commands

from blizzbot.api import BattleNetError

AUCTIONS_CACHE_TTL_SECONDS = 600
FOOTER_NOTE = (
    "Blizzard has no price history API, and this snapshot itself can lag ~1h behind "
    "the real auction house — a just-posted item may not show up yet."
)
# Confirmed by sampling (40 random listings, 0 matches) and direct spot checks
# (Sea Mist Rice Noodles, Flask of Spring Blossoms, Ghost Iron Ore all 0):
# Classic's connected-realm auctions endpoint only ever returns
# Armor/Weapon/Miscellaneous-class items. The separate "commodities" feed
# (where Blizzard normally puts stackable goods) comes back empty for Classic
# -- not populated, not just slow. So Consumables and Trade Goods (flasks,
# food, potions, herbs, ore, cloth, etc.) can never be found here, no matter
# how long you wait. Not a bug -- Blizzard just doesn't expose that data for
# Classic through any endpoint we've found.
NEVER_LISTED_CLASSES = {"Consumable", "Trade Goods"}


def format_money(copper: int) -> str:
    gold, rem = divmod(copper, 10000)
    silver, cop = divmod(rem, 100)
    parts = []
    if gold:
        parts.append(f"{gold:,}g")
    if silver:
        parts.append(f"{silver}s")
    if cop or not parts:
        parts.append(f"{cop}c")
    return " ".join(parts)


class AuctionHouse(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._connected_realm_id: int | None = None
        self._auctions_cache: tuple[float, list[dict]] | None = None

    async def _get_connected_realm_id(self) -> int:
        if self._connected_realm_id is None:
            self._connected_realm_id = await self.bot.bnet_client.connected_realm_id(
                self.bot.config.wow_realm_slug
            )
        return self._connected_realm_id

    async def _get_auctions(self) -> list[dict]:
        now = time.monotonic()
        if self._auctions_cache and now - self._auctions_cache[0] < AUCTIONS_CACHE_TTL_SECONDS:
            return self._auctions_cache[1]
        realm_id = await self._get_connected_realm_id()
        auctions = await self.bot.bnet_client.connected_realm_auctions(realm_id)
        self._auctions_cache = (now, auctions)
        return auctions

    @app_commands.command(name="ah", description="Check current Auction House prices for an item")
    @app_commands.describe(item="Item name")
    async def ah(self, interaction: discord.Interaction, item: int):
        await interaction.response.defer(ephemeral=True)

        try:
            item_data = await self.bot.bnet_client.item_by_id(item)
        except BattleNetError:
            await interaction.followup.send("Couldn't find that item.", ephemeral=True)
            return

        name = item_data.get("name", "Unknown item")
        item_class = item_data.get("item_class", {}).get("name", "")
        embed = discord.Embed(title=f"💰 {name}", color=discord.Color.gold())

        try:
            icon_url = await self.bot.bnet_client.item_icon_url(item)
            if icon_url:
                embed.set_thumbnail(url=icon_url)
        except BattleNetError:
            pass

        auctions = await self._get_auctions()
        listings = [a for a in auctions if a.get("item", {}).get("id") == item]

        if not listings:
            if item_class in NEVER_LISTED_CLASSES:
                embed.description = (
                    f"Blizzard's Classic API doesn't expose Auction House data for "
                    f"**{item_class}**-type items (confirmed — this isn't a delay, "
                    f"it just isn't there). `/ah` only works for gear/weapons/misc items."
                )
            else:
                embed.description = "No auctions currently listed for this item."
                embed.set_footer(text=FOOTER_NOTE)
            await interaction.followup.send(embed=embed, ephemeral=True)
            return

        priced = []
        for a in listings:
            is_buyout = "buyout" in a
            price = a.get("buyout") or a.get("bid")
            if not price:
                continue
            qty = a.get("quantity", 1)
            priced.append((price / qty, price, qty, is_buyout))
        priced.sort(key=lambda p: p[0])

        lines = [
            f"{format_money(total_price)}" + (f" x{qty}" if qty > 1 else "") + ("" if is_buyout else " (bid)")
            for _, total_price, qty, is_buyout in priced[:8]
        ]

        embed.add_field(name="Cheapest listings", value="\n".join(lines) or "—", inline=False)
        embed.add_field(name="Total listings", value=str(len(listings)), inline=True)
        embed.add_field(name="Total quantity", value=str(sum(p[2] for p in priced)), inline=True)
        if priced:
            embed.add_field(name="Lowest unit price", value=format_money(int(priced[0][0])), inline=True)
        embed.set_footer(text=FOOTER_NOTE)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @ah.autocomplete("item")
    async def ah_autocomplete(self, interaction: discord.Interaction, current: str):
        if len(current) < 3:
            return []
        try:
            results = await self.bot.bnet_client.search_items(current)
        except BattleNetError:
            return []
        choices = []
        for entry in results:
            name = entry.get("name")
            en_name = name.get("en_US") if isinstance(name, dict) else name
            if not en_name:
                continue
            choices.append(app_commands.Choice(name=en_name[:100], value=entry["id"]))
        return choices[:20]


async def setup(bot: commands.Bot):
    await bot.add_cog(AuctionHouse(bot))
