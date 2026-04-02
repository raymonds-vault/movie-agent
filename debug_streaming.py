import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import get_settings
from app.services.chat_service import ChatService

async def main():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession)
    
    async with session_factory() as session:
        service = ChatService(session, settings)
        try:
            async for chunk in service.stream_message("Interstellar"):
                print("CHUNK:", chunk)
        except Exception as e:
            print("EXCEPTION OUTSIDE:", e)

if __name__ == "__main__":
    asyncio.run(main())
