import logging
import urllib.parse

import httpx

from src.application.ports.ad_source import AdSnapshot, AdSource
from src.trace_context import TRACE_ID_HEADER, get_trace_id

logger = logging.getLogger(__name__)


class AdServiceAdSource(AdSource):
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url

    async def get(self, ad_id: int) -> AdSnapshot | None:
        url = urllib.parse.urljoin(self._base_url, f"internal/ads/{ad_id}")
        try:
            trace_id = get_trace_id()
            headers = {TRACE_ID_HEADER.decode(): trace_id} if trace_id else None
            resp = await self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("failed to fetch ad %s: %s", ad_id, exc)
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        return AdSnapshot(
            ad_id=data["id"],
            title=data["title"],
            description=data["description"],
            price=data["price"],
            category=data["category"],
            city=data["city"],
            status=data["status"],
        )
