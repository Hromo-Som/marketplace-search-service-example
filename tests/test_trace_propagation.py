from typing import Any

import httpx
import pytest

from src.application.services.kafka_ads_consumer import KafkaAdsConsumer
from src.infrastructure.http.ad_client import AdServiceAdSource
from src.trace_context import get_trace_id, set_trace_id, trace_id_var


@pytest.mark.asyncio
async def test_ad_client_forwards_current_trace_id() -> None:
    received_headers: httpx.Headers | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal received_headers
        received_headers = request.headers
        return httpx.Response(
            200,
            json={
                "id": 7,
                "title": "Desk",
                "description": "Wood desk",
                "price": 10,
                "category": "Furniture",
                "city": "Perm",
                "status": "active",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        source = AdServiceAdSource(client, "http://ad/")
        token = set_trace_id("trace-search")
        try:
            ad = await source.get(7)
        finally:
            trace_id_var.reset(token)

    assert ad is not None
    assert received_headers is not None
    assert received_headers["X-Trace-Id"] == "trace-search"


class FakeKafkaMessage:
    value: dict[str, Any] = {"event": "ad.created", "payload": {"ad_id": 11}}
    headers = [("x-trace-id", b"trace-consumer")]


class FakeKafkaConsumer:
    def __init__(self) -> None:
        self.messages = [FakeKafkaMessage()]
        self.commits = 0

    def __aiter__(self) -> "FakeKafkaConsumer":
        return self

    async def __anext__(self) -> FakeKafkaMessage:
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop()

    async def commit(self) -> None:
        self.commits += 1


class FakeUseCase:
    def __init__(self) -> None:
        self.trace_ids: list[str | None] = []

    async def execute(self, ad_id: int) -> None:
        self.trace_ids.append(get_trace_id())


@pytest.mark.asyncio
async def test_kafka_consumer_sets_trace_context_during_processing() -> None:
    kafka = FakeKafkaConsumer()
    index_ad = FakeUseCase()
    consumer = KafkaAdsConsumer(
        kafka,  # type: ignore[arg-type]
        index_ad,  # type: ignore[arg-type]
        FakeUseCase(),  # type: ignore[arg-type]
    )

    await consumer.run()

    assert index_ad.trace_ids == ["trace-consumer"]
    assert kafka.commits == 1
    assert get_trace_id() is None
