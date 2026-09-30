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

    async def character_specializations(self, realm_slug: str, character_name: str) -> dict:
        return await self._get(
            f"/profile/wow/character/{realm_slug}/{character_name.lower()}/specializations",
            self._config.namespace_profile,
        )

    async def character_media(self, realm_slug: str, character_name: str) -> dict:
        return await self._get(
            f"/profile/wow/character/{realm_slug}/{character_name.lower()}/character-media",
            self._config.namespace_profile,
        )

    async def search_items(self, name_query: str, limit: int = 15) -> list[dict]:
        """Partial/prefix name search (Blizzard's Search API supports a trailing
        '*' wildcard). Returns raw item `data` dicts, ranked by Blizzard's own
        relevance score -- do NOT add an `orderby`, it discards that ranking
        and alphabetizes instead, burying the actual best match."""
        result = await self._get(
            "/data/wow/search/item",
            self._config.namespace_static,
            **{"name.en_US": f"{name_query}*", "_pageSize": limit},
        )
        return [r["data"] for r in result.get("results", [])]

    async def item_by_id(self, item_id: int) -> dict:
        return await self._get(f"/data/wow/item/{item_id}", self._config.namespace_static)

    async def item_icon_url(self, item_id: int) -> str | None:
        data = await self._get(f"/data/wow/media/item/{item_id}", self._config.namespace_static)
        for asset in data.get("assets", []):
            if asset.get("key") == "icon":
                return asset.get("value")
        return None

    async def connected_realm_id(self, realm_slug: str) -> int:
        realm = await self._get(f"/data/wow/realm/{realm_slug}", self._config.namespace_dynamic)
        href = realm["connected_realm"]["href"]
        return int(href.split("/connected-realm/")[1].split("?")[0])

    async def connected_realm_auctions(self, connected_realm_id: int) -> list[dict]:
        data = await self._get(f"/data/wow/connected-realm/{connected_realm_id}/auctions", self._config.namespace_dynamic)
        return data.get("auctions", [])

    async def playable_class_icon_url(self, class_id: int) -> str | None:
        data = await self._get(f"/data/wow/media/playable-class/{class_id}", self._config.namespace_static)
        for asset in data.get("assets", []):
            if asset.get("key") == "icon":
                return asset.get("value")
        return None

    async def playable_specialization_icon_url(self, spec_id: int) -> str | None:
        data = await self._get(f"/data/wow/media/playable-specialization/{spec_id}", self._config.namespace_static)
        for asset in data.get("assets", []):
            if asset.get("key") == "icon":
                return asset.get("value")
        return None

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
