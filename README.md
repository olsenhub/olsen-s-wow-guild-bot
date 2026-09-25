# blizz_bot

Multiservice Discord bot for a WoW guild, built on the Battle.net API. Currently targets
**MoP Classic** (the Classic progression realms); designed to also support retail
(WoW Forever) later by swapping the namespace/region config.

Two services share one SQLite database:

- **`poller`** — background worker, periodically syncs the guild roster + character
  profiles from Battle.net, stores snapshots, and posts level-up / achievement milestones
  to a Discord webhook.
- **`bot`** — the interactive Discord bot: `/panel` (buttons for Leaderboards, Active
  Players, Character Lookup), plus `/leaderboard`, `/active`, `/character`, `/link`,
  `/unlink`, `/forceunlink`.

## Prerequisites

1. **Battle.net API client** — create one at https://develop.battle.net/access/clients.
   You'll get a Client ID and Client Secret (no OAuth login flow needed — the bot uses
   app-only client-credentials auth to read public guild/character data).
2. **Discord bot** — create an application at https://discord.com/developers/applications:
   - Add a Bot, copy the token.
   - Under **Privileged Gateway Intents**, enable **Server Members Intent** and
     **Presence Intent** (needed for the Active Players online-badge).
   - Under OAuth2 → URL Generator, select scopes `bot` and `applications.commands`,
     give it `Send Messages`, `Use Slash Commands`, `Embed Links`, and invite it to
     your guild's server.
   - (Optional but recommended for the "who can `/forceunlink`" gate) note the role ID
     of your officer role — right-click the role in Discord with Developer Mode on.
3. **A Discord webhook** for the level-up feed channel — channel settings → Integrations
   → Webhooks → New Webhook → copy URL.

## Setup

```bash
cp .env.example .env
# fill in .env: Discord token/webhook, Battle.net client id/secret, realm+guild slugs
```

Realm/guild slugs are the lowercase-hyphenated form used in Battle.net URLs, e.g. realm
`Area 52` → `area-52`, guild name `Some Guild` → `some-guild`.

**Verify the namespace before first full run** — Classic progression realms (which is
what MoP Classic currently runs on) use the `classic` namespace family. This has held
true across TBC/Wrath/Cata Classic, but confirm it resolves for your region:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 verify_namespace.py
```

If your realm isn't found, try `BNET_NAMESPACE_SET=classic-era` in `.env` (that's the
separate Vanilla/Season of Discovery/Hardcore track) and re-run.

## Run

```bash
docker compose up --build -d
docker compose logs -f
```

First roster sync can take a little while depending on guild size (one API call per
member). Once it completes, run `/panel` in Discord.

## Notes / known limitations

- Blizzard's API has no live character location or online status — see the "Recently
  Active" footer in-bot for what `last_login_timestamp` actually means (login time only,
  no logout signal, not guaranteed real-time).
- `/link` is first-claim, unverified (see plan doc for the reasoning) — an officer with
  the configured `OFFICER_ROLE_ID` can `/forceunlink` a mis-claimed character.
- Moving to WoW Forever later: point `BNET_NAMESPACE_SET`/`BNET_REGION` at retail
  namespaces (`profile-us`/`profile-eu`, no `classic` suffix) and update realm/guild slugs.
