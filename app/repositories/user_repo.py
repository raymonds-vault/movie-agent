"""User repository — Firebase-backed identity sync."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_firebase_uid(self, firebase_uid: str) -> User | None:
        stmt = select(User).where(User.firebase_uid == firebase_uid)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_from_claims(
        self,
        *,
        firebase_uid: str,
        email: str | None,
        display_name: str | None,
        photo_url: str | None,
        email_verified: bool,
    ) -> User:
        existing = await self.get_by_firebase_uid(firebase_uid)
        if existing:
            return await self.update(
                existing,
                email=email,
                display_name=display_name,
                photo_url=photo_url,
                email_verified=email_verified,
            )
        return await self.create(
            firebase_uid=firebase_uid,
            email=email,
            display_name=display_name,
            photo_url=photo_url,
            email_verified=email_verified,
        )
