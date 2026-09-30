from dataclasses import dataclass


@dataclass
class GuildMember:
    character_name: str
    realm_slug: str
    character_class: str
    level: int
    guild_rank: int
    last_login_timestamp: int | None
    average_item_level: int | None
    achievement_points: int | None
    updated_at: str
    active_spec: str | None = None
    active_spec_id: int | None = None


@dataclass
class CharacterSnapshot:
    character_name: str
    realm_slug: str
    level: int
    achievement_points: int
    item_level: int
    captured_at: str


@dataclass
class DiscordLink:
    discord_user_id: int
    character_name: str
    realm_slug: str
    linked_at: str
