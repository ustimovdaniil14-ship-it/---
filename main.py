import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from casino_bot import router          # твой большой файл с играми
import rubup_server

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_SERVER = TelegramAPIServer.from_base("https://bot.catup.lol")

async def main():
    logging.basicConfig(level=logging.INFO)

    session = AiohttpSession(api=API_SERVER)
    bot = Bot(BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Запускаем веб-сервер + мини-апп
    await rubup_server.start(bot)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
