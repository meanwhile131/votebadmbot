import os
import asyncio
import telegram

token = os.getenv("BOT_TOKEN")
if not token:
    raise ValueError("Set BOT_TOKEN env variable")

async def main():
    bot = telegram.Bot(token)
    async with bot:
        print(await bot.get_me())


if __name__ == '__main__':
    asyncio.run(main())