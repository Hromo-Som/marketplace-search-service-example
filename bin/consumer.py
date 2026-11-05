import asyncio
import json

import httpx
from aiokafka import AIOKafkaConsumer

from src.application.services.kafka_ads_consumer import KafkaAdsConsumer
from src.application.usecases.index_ad import IndexAd
from src.application.usecases.remove_ad import RemoveAd
from src.infrastructure.http.ad_client import AdServiceAdSource
from src.infrastructure.persistence.database import (
    create_engine,
    create_session_factory,
)
from src.infrastructure.persistence.uow import SQLAlchemyUnitOfWork
from src.settings import Settings
from src.trace_context import configure_logging


async def main() -> None:
    configure_logging()
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    consumer = AIOKafkaConsumer(
        settings.kafka_topic_ads,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    await consumer.start()

    async with httpx.AsyncClient(timeout=5.0) as client:
        ad_source = AdServiceAdSource(client, settings.ad_service_url)
        uow = SQLAlchemyUnitOfWork(session_factory)
        ads_consumer = KafkaAdsConsumer(
            consumer=consumer,
            index_ad=IndexAd(uow, ad_source),
            remove_ad=RemoveAd(uow),
        )
        try:
            await ads_consumer.run()
        finally:
            await consumer.stop()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
