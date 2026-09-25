"""Thin client for the Battle.net Game Data / Profile APIs (client-credentials flow)."""

import time

import httpx

from blizzbot.config import Config


class BattleNetError(RuntimeError):
    pass


class BattleNetClient:
    def __init__(self, config: Config):
        self._config = config
        self._client = httpx.AsyncClient(timeout=15.0)
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        resp = await self._client.post(
            f"https://{self._config.bnet_region}.battle.net/oauth/token",
            data={"grant_type": "client_credentials"},
            auth=(self._config.bnet_client_id, self._config.bnet_client_secret),
        )
        resp.raise_for_status()
        payload = resp.json()

        self._token = payload["access_token"]
        # refresh a bit early to avoid edge-of-expiry failures mid-request
        self._token_expires_at = time.monotonic() + payload["expires_in"] - 60
        return self._token

    async def _get(self, path: str, namespace: str, **params) -> dict:
        token = await self._get_token()
        resp = await self._client.get(
            f"https://{self._config.bnet_region}.api.blizzard.com{path}",
            headers={"Authorization": f"Bearer {token}"},
            params={"namespace": namespace, "locale": "en_US", **params},
        )
        if resp.status_code == 404:
            raise BattleNetError(f"Not found: {path}")
        resp.raise_for_status()
        return resp.json()

    async def realm_index(self) -> dict:
        """Used to verify the configured namespace/region actually resolves realms."""
        return await self._get("/data/wow/realm/index", self._config.namespace_dynamic)

    async def guild_roster(self) -> dict:
        c = self._config
        return await self._get(
            f"/data/wow/guild/{c.wow_realm_slug}/{c.wow_guild_slug}/roster",
            c.namespace_profile,
        )

    async def character_profile(self, realm_slug: str, character_name: str) -> dict:
        return await self._get(
            f"/profile/wow/character/{realm_slug}/{character_name.lower()}",
            self._config.namespace_profile,
        )

    async def character_equipment(self, realm_slug: str, character_name: str) -> dict:
        return await self._get(
            f"/profile/wow/character/{realm_slug}/{character_name.lower()}/equipment",
            self._config.namespace_profile,
        )

    async def character_media(self, realm_slug: str, character_name: str) -> dict:
        return await self._get(
            f"/profile/wow/character/{realm_slug}/{character_name.lower()}/character-media",
            self._config.namespace_profile,
        )

    async def resolve_icon_url(self, media_href: str) -> str | None:
        """Follows an item/spell's media href (already namespaced) to its actual
        icon image URL on Blizzard's render CDN."""
        token = await self._get_token()
        resp = await self._client.get(media_href, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            return None
        for asset in resp.json().get("assets", []):
            if asset.get("key") == "icon":
                return asset.get("value")
        return None
