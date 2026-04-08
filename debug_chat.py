import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import app.models  # noqa: F401
from app.core.auth import DEV_FIREBASE_UID
from app.models.base import Base
from app.core.config import get_settings
from app.repositories.user_repo import UserRepository
from app.services.chat_service import ChatService

async def main():
    settings = get_settings()
    # Force SQLite for debugging
    settings.DATABASE_URL = "sqlite+aiosqlite:///./debug.db"
    
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
    
    async with session_factory() as session:
        urepo = UserRepository(session)
        user = await urepo.upsert_from_claims(
            firebase_uid=DEV_FIREBASE_UID,
            email="debug@local",
            display_name="Debug",
            photo_url=None,
            email_verified=True,
        )
        await session.commit()
        service = ChatService(session, settings)
        print("Sending message...")
        try:
            async for chunk in service.stream_message("Interstellar", user_id=user.id):
                print("CHUNK:", chunk)
        except Exception as e:
            print("EXCEPTION OUTSIDE:", e)

if __name__ == "__main__":
    asyncio.run(main())
