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
    active_spec TEXT,
    active_spec_id INTEGER,
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
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    # CREATE TABLE IF NOT EXISTS won't add columns to a DB created before they existed.
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(guild_members)")}
    for column, decl in (("active_spec", "TEXT"), ("active_spec_id", "INTEGER")):
        if column not in columns:
            try:
                conn.execute(f"ALTER TABLE guild_members ADD COLUMN {column} {decl}")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # the bot and poller both call connect(); the other one got there first


def _now() -> str:
    return datetime.now(UTC).isoformat()


def upsert_guild_member(conn: sqlite3.Connection, *, character_name: str, realm_slug: str,
                         character_class: str, level: int, guild_rank: int,
                         last_login_timestamp: int | None, average_item_level: int | None,
                         achievement_points: int | None, active_spec: str | None = None,
                         active_spec_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO guild_members (
            character_name, realm_slug, character_class, level, guild_rank,
            last_login_timestamp, average_item_level, achievement_points, updated_at, active_spec,
            active_spec_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (character_name, realm_slug) DO UPDATE SET
            character_class = excluded.character_class,
            level = excluded.level,
            guild_rank = excluded.guild_rank,
            last_login_timestamp = excluded.last_login_timestamp,
            average_item_level = excluded.average_item_level,
            achievement_points = excluded.achievement_points,
            updated_at = excluded.updated_at,
            active_spec = excluded.active_spec,
            active_spec_id = excluded.active_spec_id
        """,
        (character_name, realm_slug, character_class, level, guild_rank,
         last_login_timestamp, average_item_level, achievement_points, _now(), active_spec,
         active_spec_id),
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
                 active_spec: str | None = None, limit: int = 10) -> list[sqlite3.Row]:
    column = {
        "level": "level",
        "achievement_points": "achievement_points",
        "item_level": "average_item_level",
    }[metric]
    query = (
        f"SELECT character_name, realm_slug, character_class, active_spec, {column} AS value "
        "FROM guild_members"
    )
    filters: list[str] = []
    params: list = []
    if character_class:
        filters.append("character_class = ?")
        params.append(character_class)
    if active_spec:
        filters.append("active_spec = ?")
        params.append(active_spec)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += f" ORDER BY {column} DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def specs_for_class(conn: sqlite3.Connection, character_class: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT active_spec FROM guild_members "
        "WHERE character_class = ? AND active_spec IS NOT NULL ORDER BY active_spec",
        (character_class,),
    ).fetchall()
    return [row["active_spec"] for row in rows]


def known_specs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every (class, spec, spec id) seen on the roster, for uploading spec emojis."""
    return conn.execute(
        "SELECT DISTINCT character_class, active_spec, active_spec_id FROM guild_members "
        "WHERE character_class IS NOT NULL AND active_spec IS NOT NULL AND active_spec_id IS NOT NULL"
    ).fetchall()


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
