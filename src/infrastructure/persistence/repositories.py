from typing import List

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.repositories import SearchRepository, SortKey
from src.domain.entities import SearchDocument
from src.infrastructure.persistence.models import SearchIndexModel


class SQLAlchemySearchRepository(SearchRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        ad_id: int,
        title: str,
        description: str,
        price: int,
        category: str,
        city: str,
    ) -> None:
        stmt = insert(SearchIndexModel).values(
            ad_id=ad_id,
            title=title,
            description=description,
            price=price,
            category=category,
            city=city,
            indexed_at=func.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["ad_id"],
            set_={
                "title": stmt.excluded.title,
                "description": stmt.excluded.description,
                "price": stmt.excluded.price,
                "category": stmt.excluded.category,
                "city": stmt.excluded.city,
                "indexed_at": func.now(),
            },
        )
        await self._session.execute(stmt)

    async def delete(self, ad_id: int) -> None:
        await self._session.execute(
            delete(SearchIndexModel).where(SearchIndexModel.ad_id == ad_id)
        )

    async def search(
        self,
        query: str | None,
        category: str | None,
        city: str | None,
        min_price: int | None,
        max_price: int | None,
        sort: SortKey | None,
        limit: int,
        offset: int,
    ) -> tuple[List[SearchDocument], int]:
        items_query = select(SearchIndexModel)
        count_query = select(func.count()).select_from(SearchIndexModel)

        rank = None
        if query is not None and query.strip():
            tsquery = func.plainto_tsquery("russian", query)
            rank = func.ts_rank(SearchIndexModel.ts_vector, tsquery)
            items_query = items_query.where(
                SearchIndexModel.ts_vector.op("@@")(tsquery)
            )  # noqa: E501
            count_query = count_query.where(
                SearchIndexModel.ts_vector.op("@@")(tsquery)
            )  # noqa: E501

        if category is not None:
            items_query = items_query.where(SearchIndexModel.category == category)
            count_query = count_query.where(SearchIndexModel.category == category)
        if city is not None:
            items_query = items_query.where(SearchIndexModel.city == city)
            count_query = count_query.where(SearchIndexModel.city == city)
        if min_price is not None:
            items_query = items_query.where(SearchIndexModel.price >= min_price)
            count_query = count_query.where(SearchIndexModel.price >= min_price)
        if max_price is not None:
            items_query = items_query.where(SearchIndexModel.price <= max_price)
            count_query = count_query.where(SearchIndexModel.price <= max_price)

        items_query = _apply_sort(items_query, sort, rank).limit(limit).offset(offset)

        items_result = await self._session.execute(items_query)
        count_result = await self._session.execute(count_query)
        models = items_result.scalars().all()
        total = count_result.scalar_one()
        return [_to_entity(m) for m in models], total

    async def suggest(
        self,
        prefix: str,
        limit: int,
    ) -> list[str]:
        stmt = (
            select(SearchIndexModel.title)
            .where(SearchIndexModel.title.ilike(f"{prefix}%"))
            .distinct()
            .order_by(SearchIndexModel.title.asc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [row[0] for row in result.all()]


def _apply_sort(query, sort: SortKey | None, rank):
    if sort == "price_asc":
        return query.order_by(SearchIndexModel.price.asc())
    if sort == "price_desc":
        return query.order_by(SearchIndexModel.price.desc())
    if sort == "date":
        return query.order_by(SearchIndexModel.indexed_at.desc())
    if rank is not None:
        return query.order_by(rank.desc())
    return query.order_by(SearchIndexModel.indexed_at.desc())


def _to_entity(model: SearchIndexModel) -> SearchDocument:
    return SearchDocument(
        id=model.id,
        ad_id=model.ad_id,
        title=model.title,
        description=model.description,
        price=model.price,
        category=model.category,
        city=model.city,
        indexed_at=model.indexed_at,
    )
