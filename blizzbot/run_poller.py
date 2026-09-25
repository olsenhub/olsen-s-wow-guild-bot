"""Background worker: periodically syncs guild roster + character profiles from the
Battle.net API into SQLite, and posts level-up / achievement milestones to a Discord webhook.
"""

import asyncio
import logging

import httpx

from blizzbot import db
from blizzbot.api import BattleNetClient, BattleNetError
from blizzbot.config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("poller")


async def post_webhook(webhook_url: str, content: str) -> None:
    if not webhook_url:
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(webhook_url, json={"content": content})
        if resp.status_code >= 300:
            log.warning("Webhook post failed (%s): %s", resp.status_code, resp.text)


async def sync_once(client: BattleNetClient, conn, config) -> None:
    roster = await client.guild_roster()
    members = roster.get("members", [])
    log.info("Fetched roster: %d members", len(members))

    for entry in members:
        character = entry["character"]
        realm_slug = character["realm"]["slug"]
        name = character["name"]
        guild_rank = entry.get("rank")

        try:
            profile = await client.character_profile(realm_slug, name)
        except BattleNetError:
            log.warning("Could not fetch profile for %s-%s (privacy flag or not found)", name, realm_slug)
            continue

        level = profile.get("level", character.get("level"))
        item_level = profile.get("average_item_level")
        achievement_points = profile.get("achievement_points", 0)
        last_login = profile.get("last_login_timestamp")
        char_class = profile.get("character_class", {}).get("name")

        previous = db.get_member(conn, name, realm_slug)

        db.upsert_guild_member(
            conn,
            character_name=name,
            realm_slug=realm_slug,
            character_class=char_class,
            level=level,
            guild_rank=guild_rank,
            last_login_timestamp=last_login,
            average_item_level=item_level,
            achievement_points=achievement_points,
        )
        db.insert_snapshot(
            conn,
            character_name=name,
            realm_slug=realm_slug,
            level=level,
            achievement_points=achievement_points,
            item_level=item_level or 0,
        )

        if previous is not None:
            if previous["level"] is not None and level > previous["level"]:
                await post_webhook(
                    config.discord_webhook_url,
                    f"🎉 **{name}** dinged level **{level}** (was {previous['level']})!",
                )
            prev_ap = previous["achievement_points"] or 0
            if achievement_points > prev_ap + 50:
                await post_webhook(
                    config.discord_webhook_url,
                    f"🏆 **{name}** earned achievements! ({prev_ap} → {achievement_points} points)",
                )


async def main() -> None:
    config = load_config()
    conn = db.connect(config.database_path)
    client = BattleNetClient(config)

    interval_seconds = config.poll_interval_minutes * 60
    try:
        while True:
            try:
                await sync_once(client, conn, config)
            except Exception:
                log.exception("Sync cycle failed")
            log.info("Sleeping %d minutes until next sync", config.poll_interval_minutes)
            await asyncio.sleep(interval_seconds)
    finally:
        await client.aclose()
        conn.close()


if __name__ == "__main__":
    asyncio.run(main())
