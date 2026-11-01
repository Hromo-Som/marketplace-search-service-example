from src.application.ports.uow import UnitOfWork
from src.application.ports.usecases import RemoveAdPort


class RemoveAd(RemoveAdPort):
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, ad_id: int) -> None:
        async with self._uow as uow:
            await uow.search.delete(ad_id)
            await uow.commit()
