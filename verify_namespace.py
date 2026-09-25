"""One-off check: confirm the configured BNET_NAMESPACE_SET/BNET_REGION actually
resolves realms before the rest of the stack is built on top of it.

Usage: python3 verify_namespace.py
"""

import asyncio

from blizzbot.api import BattleNetClient
from blizzbot.config import load_config


async def main() -> None:
    config = load_config()
    client = BattleNetClient(config)
    try:
        print(f"Checking namespace '{config.namespace_dynamic}' in region '{config.bnet_region}'...")
        data = await client.realm_index()
        realms = data.get("realms", [])
        print(f"OK: {len(realms)} realms found.")
        for realm in realms[:15]:
            print(f"  - {realm['name']} ({realm['slug']})")
        if config.wow_realm_slug:
            match = next((r for r in realms if r["slug"] == config.wow_realm_slug), None)
            if match:
                print(f"\nConfigured WOW_REALM_SLUG='{config.wow_realm_slug}' found: {match['name']}")
            else:
                print(
                    f"\nWARNING: WOW_REALM_SLUG='{config.wow_realm_slug}' was NOT found in this "
                    "namespace. Double check BNET_NAMESPACE_SET (try 'classic-era' instead of "
                    "'classic', or vice versa) and BNET_REGION."
                )
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
