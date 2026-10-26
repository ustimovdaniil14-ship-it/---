import asyncio
from aiohttp import web
import os

async class RubupServer:
    def __init__(self, bot):
        self.bot = bot
        self.app = web.Application()
        self.app.router.add_get('/', self.handle)
        self.app.router.add_get('/health', self.handle)
        self.runner = None

    async def handle(self, request):
        return web.Response(text="Bot is running!")

    async def start(self):
        port = int(os.environ.get("PORT", 10000))
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", port)
        await site.start()
        print(f"Web server started on port {port}")

async def start(module, bot):
    server = RubupServer(bot)
    await server.start()
  
