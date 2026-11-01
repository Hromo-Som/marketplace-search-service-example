from src.application.ports.ad_source import AdSource
from src.application.ports.uow import UnitOfWork
from src.application.ports.usecases import IndexAdPort


class IndexAd(IndexAdPort):
    def __init__(self, uow: UnitOfWork, ad_source: AdSource) -> None:
        self._uow = uow
        self._ad_source = ad_source

    async def execute(self, ad_id: int) -> None:
        ad = await self._ad_source.get(ad_id)
        async with self._uow as uow:
            if ad is None or ad.status != "active":
                await uow.search.delete(ad_id)
            else:
                await uow.search.upsert(
                    ad_id=ad.ad_id,
                    title=ad.title,
                    description=ad.description,
                    price=ad.price,
                    category=ad.category,
                    city=ad.city,
                )
            await uow.commit()
