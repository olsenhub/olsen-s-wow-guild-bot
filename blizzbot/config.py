import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    discord_bot_token: str
    discord_webhook_url: str
    discord_guild_id: int | None
    officer_role_id: int | None

    bnet_client_id: str
    bnet_client_secret: str
    bnet_region: str
    bnet_namespace_set: str

    wow_realm_slug: str
    wow_guild_slug: str

    poll_interval_minutes: int
    database_path: str

    @property
    def namespace_profile(self) -> str:
        return f"profile-{self.bnet_namespace_set}-{self.bnet_region}"

    @property
    def namespace_dynamic(self) -> str:
        return f"dynamic-{self.bnet_namespace_set}-{self.bnet_region}"

    @property
    def namespace_static(self) -> str:
        return f"static-{self.bnet_namespace_set}-{self.bnet_region}"


def load_config() -> Config:
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    officer_role_id = os.environ.get("OFFICER_ROLE_ID")
    return Config(
        discord_bot_token=os.environ.get("DISCORD_BOT_TOKEN", ""),
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL", ""),
        discord_guild_id=int(guild_id) if guild_id else None,
        officer_role_id=int(officer_role_id) if officer_role_id else None,
        bnet_client_id=_required("BLIZZARD_CLIENT_ID"),
        bnet_client_secret=_required("BLIZZARD_CLIENT_SECRET"),
        bnet_region=os.environ.get("BNET_REGION", "eu"),
        bnet_namespace_set=os.environ.get("BNET_NAMESPACE_SET", "classic"),
        wow_realm_slug=_required("WOW_REALM_SLUG"),
        wow_guild_slug=_required("WOW_GUILD_SLUG"),
        poll_interval_minutes=int(os.environ.get("POLL_INTERVAL_MINUTES", "30")),
        database_path=os.environ.get("DATABASE_PATH", "./data/blizzbot.sqlite3"),
    )
