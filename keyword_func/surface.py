import re
from asyncio import sleep


def parseJdCom(message, reg):
    rst = re.search(reg, message, re.S)
    return f"`{rst.group(1)} {rst.group(2)}/`"


async def main(context, type, reg):
    if type == 1:
        await context.client.send_message(context.chat_id, f"{parseJdCom(context.text, reg)}", reply_to=context.id)
        await sleep(1)
        await context.delete()
    elif type == 2:
        await context.edit(f"{parseJdCom(context.text, reg)}")
    return ""
