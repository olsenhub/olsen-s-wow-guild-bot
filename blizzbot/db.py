import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_members (
    character_name TEXT NOT NULL,
    realm_slug TEXT NOT NULL,
    character_class TEXT,
    level INTEGER,
    guild_rank INTEGER,
    last_login_timestamp INTEGER,
    average_item_level INTEGER,
    achievement_points INTEGER,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (character_name, realm_slug)
);

CREATE TABLE IF NOT EXISTS character_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_name TEXT NOT NULL,
    realm_slug TEXT NOT NULL,
    level INTEGER,
    achievement_points INTEGER,
    item_level INTEGER,
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_char_time
    ON character_snapshots (character_name, realm_slug, captured_at);

CREATE TABLE IF NOT EXISTS discord_links (
    discord_user_id INTEGER NOT NULL,
    character_name TEXT NOT NULL,
    realm_slug TEXT NOT NULL,
    linked_at TEXT NOT NULL,
    UNIQUE (character_name, realm_slug)
);
"""


def connect(database_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat()


def upsert_guild_member(conn: sqlite3.Connection, *, character_name: str, realm_slug: str,
                         character_class: str, level: int, guild_rank: int,
                         last_login_timestamp: int | None, average_item_level: int | None,
                         achievement_points: int | None) -> None:
    conn.execute(
        """
        INSERT INTO guild_members (
            character_name, realm_slug, character_class, level, guild_rank,
            last_login_timestamp, average_item_level, achievement_points, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (character_name, realm_slug) DO UPDATE SET
            character_class = excluded.character_class,
            level = excluded.level,
            guild_rank = excluded.guild_rank,
            last_login_timestamp = excluded.last_login_timestamp,
            average_item_level = excluded.average_item_level,
            achievement_points = excluded.achievement_points,
            updated_at = excluded.updated_at
        """,
        (character_name, realm_slug, character_class, level, guild_rank,
         last_login_timestamp, average_item_level, achievement_points, _now()),
    )
    conn.commit()


def get_member(conn: sqlite3.Connection, character_name: str, realm_slug: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM guild_members WHERE character_name = ? AND realm_slug = ?",
        (character_name, realm_slug),
    ).fetchone()


def search_member_names(conn: sqlite3.Connection, prefix: str, limit: int = 25) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT character_name, realm_slug FROM guild_members "
        "WHERE character_name LIKE ? ORDER BY character_name LIMIT ?",
        (f"{prefix}%", limit),
    ).fetchall()


def latest_snapshot_before(conn: sqlite3.Connection, character_name: str, realm_slug: str,
                            before: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM character_snapshots WHERE character_name = ? AND realm_slug = ? "
        "AND captured_at < ? ORDER BY captured_at DESC LIMIT 1",
        (character_name, realm_slug, before),
    ).fetchone()


def insert_snapshot(conn: sqlite3.Connection, *, character_name: str, realm_slug: str,
                     level: int, achievement_points: int, item_level: int) -> None:
    conn.execute(
        "INSERT INTO character_snapshots "
        "(character_name, realm_slug, level, achievement_points, item_level, captured_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (character_name, realm_slug, level, achievement_points, item_level, _now()),
    )
    conn.commit()


def leaderboard(conn: sqlite3.Connection, metric: str, character_class: str | None = None,
                 limit: int = 10) -> list[sqlite3.Row]:
    column = {
        "level": "level",
        "achievement_points": "achievement_points",
        "item_level": "average_item_level",
    }[metric]
    query = f"SELECT character_name, realm_slug, character_class, {column} AS value FROM guild_members"
    params: list = []
    if character_class:
        query += " WHERE character_class = ?"
        params.append(character_class)
    query += f" ORDER BY {column} DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def recently_active(conn: sqlite3.Connection, limit: int = 15) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM guild_members WHERE last_login_timestamp IS NOT NULL "
        "ORDER BY last_login_timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()


def link_character(conn: sqlite3.Connection, discord_user_id: int, character_name: str,
                    realm_slug: str) -> bool:
    """Returns False if the character is already linked to someone (first-claim-wins)."""
    try:
        conn.execute(
            "INSERT INTO discord_links (discord_user_id, character_name, realm_slug, linked_at) "
            "VALUES (?, ?, ?, ?)",
            (discord_user_id, character_name, realm_slug, _now()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def unlink_own(conn: sqlite3.Connection, discord_user_id: int) -> int:
    cur = conn.execute("DELETE FROM discord_links WHERE discord_user_id = ?", (discord_user_id,))
    conn.commit()
    return cur.rowcount


def force_unlink(conn: sqlite3.Connection, character_name: str, realm_slug: str) -> int:
    cur = conn.execute(
        "DELETE FROM discord_links WHERE character_name = ? AND realm_slug = ?",
        (character_name, realm_slug),
    )
    conn.commit()
    return cur.rowcount


def get_link_for_discord_user(conn: sqlite3.Connection, discord_user_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM discord_links WHERE discord_user_id = ?", (discord_user_id,)
    ).fetchone()


def all_links(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM discord_links").fetchall()
