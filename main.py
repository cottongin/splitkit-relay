#!/usr/bin/env python3
# ruff: noqa: E501, F841

from dotenv import dotenv_values
from asif.bot import Client, Channel
from asif.util import bold, no_highlight

import aiohttp
import asyncio
import json
import socketio
import re
import urllib.parse as ul


CONFIG = dotenv_values(".env")
URL = CONFIG.get("URL")


MESSAGES = {}
try:
    with open("MESSAGES.json", "r") as f:
        MESSAGES = json.load(f)
except Exception as err:
    print(err)
    pass
CHANNELS = ["#skr", "#greenroom"]
NSPASS = CONFIG.get("NSPASS")

ADMINS = [
    "cottongin",
    "SirSpencer",
    "DuhLaurien",
    "boo-bury",
    "lavish",
    "SirVo",
    "adamc1999",
    "dave",
]

TEXTTOSTRIP = "Text - click to edit"

bot = Client(
    host="irc.zeronode.net",
    port=6697,
    secure=True,
    user="splitkit-relay",
    realname="splitkit relay",
    nick="splitkit-relay",
)

socket = socketio.AsyncClient()


@socket.event(namespace="/event")
async def connect():
    print("connection established")


###
# Main stuff
###


@socket.on("*", namespace="/event")
async def my_message(event, data):
    """Main socket listener"""
    global MESSAGES

    _ = data.pop("value", None)  # remove value information that the relay doesn't use
    print(f"Event received: {event}\nMessage: {data}")

    # set the last message to nothing so the relay does not emit something is playing when `np is used
    if not data:
        MESSAGES["lastMsg"] = "nothing"
        return

    # compare the block GUID to the last message the relay sent so it doesn't spam events
    guid = data.get("blockGuid", "guid")
    if guid == MESSAGES.get("activeGUID"):
        return

    # begin plucking relevant data out
    image = data.get("image", "N/A")
    # wavlake fix
    if "cloudfront" in image:
        u = ul.quote_plus(image)
        image = f"https://www.wavlake.com/_next/image?url={u}&w=750&q=75"

    # Shorten long image URLs
    params = {
        "signature": CONFIG.get("SHORTURL"),
        "action": "shorturl",
        "url": str(image),
        "format": "json",
    }
    shortURLJSON = await postToYourls(params)
    image = shortURLJSON.get("shorturl", image)

    title = data.get("title", "").replace(TEXTTOSTRIP, "").strip()
    title = " ".join(title.split())
    title = bold("{0}".format(title))

    # remove junk default datas
    line = data.get("line", [""])
    try:
        line.remove(TEXTTOSTRIP)
    except ValueError as _:
        pass

    details = " • ".join(filter(None, line)).strip()
    if " • " == details:
        details = ""
    elif "•" == details:
        details = ""
    if details:
        details = " ".join(details.split())

    urls = data.get("link", {}).get("url", "").strip()
    urls = urls.replace(TEXTTOSTRIP, "")

    # join everything together and stip newlines
    message = " - ".join(filter(None, [title, details, urls]))
    message = message.replace("\n", "")
    message = message.replace(TEXTTOSTRIP, "")
    message = message.strip()
    message = " ".join(message.split())

    # emit message
    for chan in CHANNELS:
        await bot.message(chan, f"{image}")
        await bot.message(chan, f"Now Playing: {message}")

    # setup spam detection and `np functionality
    MESSAGES["activeGUID"] = guid
    MESSAGES["lastMsg"] = message
    MESSAGES["lastImg"] = image


###
# Other stuff
###


async def postToYourls(params={}):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://therelay.cc/yourls-api.php", params=params
            ) as resp:
                print(resp.status)
                return await resp.json()
    except Exception as err:
        print(err)
        return {}


@socket.event(namespace="/event")
async def disconnect():
    print(f"disconnected from server")


@bot.on_connected()
async def connected():
    nickserv_ok = bot.await_message(
        sender="NickServ", message=re.compile("Password accepted")
    )
    await bot.message("NickServ", "IDENTIFY {}".format(NSPASS))
    await nickserv_ok
    for chan in CHANNELS:
        await bot.join(chan)
    if "splitkit" in URL:
        uuid = URL.split("live/")[-1].replace("/", "")
        URL = f"https://curiohoster.com/event?event_id={uuid}"
    await socket.connect(URL, namespaces=["/event"])


@bot.on_message(re.compile("^`join"))
async def join(message):
    if message.sender.name not in ADMINS:
        return
    channel = message.text.partition(" ")[2]
    global CHANNELS
    try:
        await bot.join(channel)
        CHANNELS.append(channel)
    except Exception as err:
        print(err)
        await bot.get_user("cottongin").message("error joining {}".format(channel))


@bot.on_message(
    matcher=lambda msg: isinstance(msg.recipient, Channel)
    and msg.text.startswith("`part")
)
async def part(message):
    if message.sender.name not in ADMINS:
        return
    await message.recipient.part()
    await bot.get_user("cottongin").message("Left {}".format(message.recipient))


@bot.on_message(re.compile("^`connect"))
async def con(message):
    if message.sender.name not in ADMINS:
        return
    try:
        url = message.text.partition(" ")[2]
        url = url.strip()
    except KeyError as err:
        print(err)
        url = URL
    if "splitkit" in url:
        uuid = url.split("live/")[-1].replace("/", "")
        url = f"https://curiohoster.com/event?event_id={uuid}"
    await socket.disconnect()
    await socket.wait()
    try:
        await socket.connect(url, namespaces=["/event"])
        await message.reply("Connected!")
    except Exception as err:
        print(err)
        await message.reply("I couldn't connect")


@bot.on_message(re.compile("^`quit"))
async def quit(message):
    if message.sender.name not in ADMINS:
        return
    try:
        with open("MESSAGES.json", "w") as f:
            json.dump(MESSAGES, f)
    except Exception as err:
        print(err)
        pass
    try:
        text = message.text.partition(" ")[2].strip()
    except Exception as err:
        print(err)
        text = "Goodbye!"
    await socket.disconnect()
    await bot.quit(text or "Goodbye!")


@bot.on_message(re.compile("^`disconnect"))
async def discon(message):
    if message.sender.name not in ADMINS:
        return
    await socket.disconnect()
    await message.reply("Disconnected")


@bot.on_message(re.compile("^`np"))
async def np(message):
    image = MESSAGES.get("lastImg")
    if image:
        await message.reply(image)
    await message.reply(f"Now Playing: {MESSAGES.get('lastMsg', 'nothing')}")


@bot.on_message(re.compile("^`ping"))
async def pong(message):
    await message.reply("pong" + message.text[5:])


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    tasks = asyncio.gather(asyncio.ensure_future(bot.run()))

    try:
        loop.run_until_complete(tasks)
    except KeyboardInterrupt as e:
        print(e)
        print("Caught keyboard interrupt. Canceling tasks...")
        tasks.cancel()
        loop.run_forever()
        tasks.exception()
    finally:
        loop.close()
