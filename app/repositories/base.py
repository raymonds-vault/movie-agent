"""
Generic base repository providing reusable CRUD operations.
All feature repositories extend this to avoid code duplication.
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Generic async CRUD repository.

    Usage:
        class MovieRepo(BaseRepository[CachedMovie]):
            def __init__(self, session):
                super().__init__(CachedMovie, session)
    """

    def __init__(self, model: type[ModelType], session: AsyncSession):
        self._model = model
        self._session = session

    async def create(self, **kwargs: Any) -> ModelType:
        """Create and return a new instance."""
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def get_by_id(self, id_value: Any) -> ModelType | None:
        """Fetch a single record by primary key."""
        return await self._session.get(self._model, id_value)

    async def get_all(
        self,
        offset: int = 0,
        limit: int = 100,
        order_by: Any = None,
    ) -> list[ModelType]:
        """Fetch multiple records with pagination."""
        stmt = select(self._model)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        """Return total count of records."""
        stmt = select(func.count()).select_from(self._model)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update(self, instance: ModelType, **kwargs: Any) -> ModelType:
        """Update an existing instance."""
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def delete(self, instance: ModelType) -> None:
        """Delete an instance."""
        await self._session.delete(instance)
        await self._session.flush()
