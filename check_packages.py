import asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.payments.models import CreditPackage
from app.shared.config import settings

async def check_packages():
    engine = create_async_engine(settings.database_url, echo=False)
    async with AsyncSession(engine) as db:
        result = await db.execute(select(CreditPackage))
        packages = result.scalars().all()
        print(f'Packages found: {len(packages)}')
        for p in packages:
            print(f'  - {p.name}: {p.credits} credits, ${p.price} USD')
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_packages())
