""" Pagermaid plugin base. """

from os import remove
from os.path import exists
from youtube_dl import YoutubeDL
from re import compile as regex_compile
from main import cmd, par, des, prefix_str
from pyrogram import Client, filters

cmd.append("ytdl")
par.append("<url>.")
des.append("上传 Youtube、Bilibili 视频到 telegram")

@Client.on_message(filters.me & filters.command("ytdl", list(prefix_str)))
async def ybdl(client, message):
    url = " ".join(message.text.split(" ")[1:])
    reply = message.reply_to_message
    reply_id = None
    await message.edit("获取视频中 . . .")
    if reply:
        reply_id = reply.message_id
    if url is None:
        await message.edit("出错了呜呜呜 ~ 无效的参数。")
        return

    youtube_pattern = regex_compile(r"^(http(s)?://)?((w){3}.)?youtu(be|.be)?(\.com)?/.+")
    if youtube_pattern.match(url):
        if not await fetch_video(client, url, message.chat.id, reply_id):
            await message.edit("出错了呜呜呜 ~ 视频下载失败。")
        # await log(f"已拉取UTB视频，地址： {url}.")
        await message.edit("视频获取成功！")


async def fetch_video(client, url, chat_id, reply_id):
    """ Extracts and uploads YouTube video. """
    youtube_dl_options = {
        'format': 'bestvideo[height=720]+bestaudio/best',
        'outtmpl': "video.%(ext)s",
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }]
    }
    YoutubeDL(youtube_dl_options).download([url])
    if not exists("video.mp4"):
        return False
    await client.send_video(
         chat_id,
         "video.mp4",
         reply_to_message_id=reply_id
    )
    remove("video.mp4")
    return True
