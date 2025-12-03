import os
import botpy
from dotenv import load_dotenv
from botpy import logging
from botpy.message import GroupMessage
from botpy.message import C2CMessage
from anuneko import *

_log = logging.get_logger()

class MyClient(botpy.Client):
    async def on_group_at_message_create(self, message: GroupMessage):
        reply = await handle(message.author.member_openid, message.content)
        result = await message.reply(content=reply)
        _log.info(result)

    async def on_c2c_message_create(self, message: C2CMessage):
        reply = await handle(message.author.user_openid, message.content)
        result = await message.reply(content=reply)
        _log.info(result)

if __name__ == "__main__":
    load_dotenv()
    intents = botpy.Intents(public_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=os.getenv("APPID"), secret=os.getenv("SECRET"))
