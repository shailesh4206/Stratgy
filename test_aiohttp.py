import aiohttp
import asyncio

async def main():
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.telegram.org") as r:
            print("Telegram:", r.status)

    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.binance.com/api/v3/time") as r:
            print("Binance:", r.status)

asyncio.run(main())