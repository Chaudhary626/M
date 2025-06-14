import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from db import init_db, remove_expired_tasks_and_proofs
from handlers import router as user_router
from admin import router as admin_router
from utils import get_token

async def daily_cleanup():
    from asyncio import sleep
    while True:
        remove_expired_tasks_and_proofs()
        await sleep(24*60*60)  # Run every 24h

async def main():
    init_db()
    bot = Bot(token=get_token())
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(user_router)
    dp.include_router(admin_router)
    # Start daily cleanup
    asyncio.create_task(daily_cleanup())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())