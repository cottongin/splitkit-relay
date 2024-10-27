#!/usr/bin/env python3
# ruff: noqa: E501, F841

from dotenv import dotenv_values
import colorlog
from asif.bot import Client, Channel
from asif.util import bold, no_highlight

import aiohttp
import argparse
import asyncio
import json
import socketio
import re
import sys
import urllib.parse as ul

import datetime

# setup logging
parser = argparse.ArgumentParser()
parser.add_argument(
    "-l",
    "--loglevel",
    default="warning",
    help="Provide logging level. Example --loglevel debug, default=warning",
)
args = parser.parse_args()
colorlog.basicConfig(
    level=args.loglevel.upper(),
)
logger = colorlog.getLogger()
stdout = colorlog.StreamHandler(stream=sys.stdout)
fmt = colorlog.ColoredFormatter(
    "%(white)s%(asctime)s%(reset)s | %(name)-15s | %(log_color)s%(levelname)-8s%(reset)s | %(blue)s%(filename)s:%(lineno)s%(reset)s | %(process)d >>> %(log_color)s%(message)s%(reset)s"
)
stdout.setFormatter(fmt)
if logger.hasHandlers():
    logger.handlers.clear()
logger.propagate = False
logger.addHandler(stdout)
logger.info("Logger initialized.")

# load .env file
CONFIG = dotenv_values(".env")

# load admins
ADMINS = None
try:
    ADMINS = CONFIG.get("ADMINS")
    ADMINS = ADMINS.split(",")
except AttributeError as _:
    # if we don't have any admins, we can't control the bot from IRC
    logger.error("ERROR: You need to configure at least one bot admin")
    sys.exit()
except Exception as err:
    logger.exception(err)
    sys.exit()
# sanity
if not ADMINS:
    logger.error("ERROR: You need to configure at least one bot admin")
    sys.exit()

# load the rest of the configuration
URL = CONFIG.get("URL", "")
try:
    CHANNELS = CONFIG.get("CHANNELS")
    CHANNELS = CHANNELS.split(",")
except Exception as err:
    logger.exception(err)
    CHANNELS = []
finally:
    CHANNELS.append("#skr")  # always join testing channel
    CHANNELS = list(set(CHANNELS))  # dedupe, just in case


# load previous data
MESSAGES = {}
try:
    with open("MESSAGES.json", "r") as f:
        MESSAGES = json.load(f)
except Exception as err:
    logger.exception(err)
    pass
NSPASS = CONFIG.get("NSPASS")


# splitkit puts default text into fields if the producer leaves them blank, but we don't
# need to see that on IRC
TEXTTOSTRIP = CONFIG.get("TEXTTOSTRIP", "Text - click to edit")

sec = True if CONFIG.get("SECURE") else False
bot = Client(
    host=CONFIG.get("HOST"),
    port=CONFIG.get("PORT"),
    secure=sec,
    user=CONFIG.get("USER"),
    realname=CONFIG.get("REALNAME"),
    nick=CONFIG.get("NICK"),
)

socket = socketio.AsyncClient()


@socket.event(namespace="/event")
async def connect():
    logger.info("connection established")


###
# Main stuff
###


@socket.on("*", namespace="/event")
async def my_message(event, data):
    """Main socket listener"""
    global MESSAGES

    if event != "remoteValue":
        return

    try:
        _ = data.pop(
            "value", None
        )  # remove value information that the relay doesn't use
    except AttributeError as err:
        logger.info(data)
        pass
    except Exception as err:
        logger.error(err)
    logger.info(f"Event received: {event}\nMessage: {data}")

    # _ = data.pop("value", None)  # remove value information that the relay doesn't use
    # logger.info(f"Event received: {event}\nMessage: {data}")

    now = int(datetime.datetime.utcnow().timestamp())
    then = MESSAGES.get("timestamp", 0)
    if now == then:
        return
    MESSAGES["timestamp"] = now

    # set the last message to nothing so the relay does not emit something is playing when `np is used
    if not data:
        MESSAGES["lastMsg"] = "nothing"
        return

    # compare the block GUID to the last message the relay sent so it doesn't spam events
    guid = data.get("blockGuid", "guid")
    logger.info(f"GUIDS: {guid}\t||\t{MESSAGES.get('activeGUID')}")
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
        logger.warning(_)
        pass
    except Exception as _:
        logger.exception(_)
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

    # # emit message
    # logger.info("Channels: {}".format(", ".join(c for c in CHANNELS)))
    # for chan in CHANNELS:
    #     await bot.message(chan, f"{image}")
    #     await bot.message(chan, f"Now Playing: {message}")

    # emit message
    channels = bot._channels
    # print(channels)
    logger.info("Channels: {}".format(", ".join(c for c in CHANNELS)))
    for chan in channels.keys():
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
                CONFIG.get("YOURLSAPIURL"), params=params
            ) as resp:
                logger.debug(resp.status)
                return await resp.json()
    except Exception as err:
        logger.exception(err)
        return {}


@socket.event(namespace="/event")
async def disconnect():
    logger.info(f"disconnected from server")


@bot.on_connected()
async def connected():
    global URL, MESSAGES
    nickserv_ok = bot.await_message(
        sender="NickServ", message=re.compile("Password accepted")
    )
    await bot.message("NickServ", "IDENTIFY {}".format(NSPASS))
    await nickserv_ok
    for chan in CHANNELS:
        logger.debug(f"Joining {chan}")
        await bot.join(chan)
    if URL:
        # from .env file
        if "splitkit" in URL:
            # swap out the splitkit URL with the curiohoster websocket direct
            uuid = URL.split("live/")[-1].replace("/", "")
            URL = f"https://curiohoster.com/event?event_id={uuid}"
        await socket.connect(URL, namespaces=["/event"])
    else:
        # we're connecting to a new event, later, so reset the old now playing info
        MESSAGES = {
            "lastImg": "",
            "lastMsg": "nothing",
            "activeGUID": "",
        }


@bot.on_message(re.compile("^`reset"))
async def reset(message):
    if message.sender.name not in ADMINS:
        return
    global MESSAGES, CHANNELS
    try:
        MESSAGES = {
            "lastImg": "",
            "lastMsg": "nothing",
            "activeGUID": "",
        }
        # reset channels, this hopefully prevents multiple messages?
        CHANNELS = []
        # for channel in bot._channels.values():
        #     CHANNELS.append(channel.name)
        # bot.part(channel)
        # now leave every channel
        for chan in bot._channels.values():
            bot.part(chan)
        CHANNELS.append("#skr")  # always join testing channel
        # CHANNELS = list(set(CHANNELS))  # dedupe, just in case
        bot.join("#skr")  # always join testing channel
        await message.reply("Done")
    except Exception as err:
        logger.exception(err)
        # the first nick in the ADMINS list is considered the primary bot operator
        # this will send a message to them saying the /join failed
        target = ADMINS[0]
        await bot.get_user(target).message("error resetting MESSAGES {}".format(err))


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
        logger.exception(err)
        # the first nick in the ADMINS list is considered the primary bot operator
        # this will send a message to them saying the /join failed
        target = ADMINS[0]
        await bot.get_user(target).message("error joining {}".format(channel))


@bot.on_message(
    matcher=lambda msg: isinstance(msg.recipient, Channel)
    and msg.text.startswith("`part")
)
async def part(message):
    if message.sender.name not in ADMINS:
        return
    global CHANNELS
    chan = message.recipient.name
    try:
        print(CHANNELS, chan)
        CHANNELS.remove(chan)
    except Exception as err:
        logger.exception(err)
        pass
    await message.recipient.part("adios")
    # the first nick in the ADMINS list is considered the primary bot operator
    # this will send a message to them saying the bot left a channel
    target = ADMINS[0]
    await bot.get_user(target).message("Left {}".format(message.recipient.name))


@bot.on_message(re.compile("^`linkme[A-Za-z0-9]+"))
@bot.on_message(re.compile("^`linkme$"))
async def linkme(message):
    if URL:
        url = URL
        uuid = url.split("=")[1]
        await message.reply(
            f"Follow along at: https://thesplitkit.com/live/{str(uuid)}"
        )
    else:
        await message.reply("I'm not connected to an event.")


@bot.on_message(re.compile("^`connect"))
async def con(message):
    global URL, MESSAGES
    if message.sender.name not in ADMINS:
        return
    try:
        url = message.text.partition(" ")[2]
        url = url.strip()
    except KeyError as err:
        logger.warning(f"URL error: {err}")
        url = URL
    if "splitkit" in url:
        uuid = url.split("live/")[-1].replace("/", "")
        url = f"https://curiohoster.com/event?event_id={uuid}"
    else:
        uuid = url.split("=")[1]
    MESSAGES = {
        "lastImg": "",
        "lastMsg": "nothing",
        "activeGUID": "",
    }
    await socket.disconnect()
    await socket.wait()
    try:
        await socket.connect(url, namespaces=["/event"])
        follow_along = f"https://thesplitkit.com/live/{str(uuid)}"
        await message.reply(f"Connected! Follow along at: {follow_along}")
        URL = url
    except Exception as err:
        logger.exception(err)
        await message.reply("I couldn't connect")


@bot.on_message(re.compile("^`quit"))
async def quit(message):
    if message.sender.name not in ADMINS:
        return
    try:
        with open("MESSAGES.json", "w") as f:
            json.dump(MESSAGES, f)
    except Exception as err:
        logger.error(err)
        pass
    try:
        text = message.text.partition(" ")[2].strip()
    except Exception as err:
        logger.exception(err)
        text = "Goodbye!"
    await socket.disconnect()
    await bot.quit(text or "Goodbye!")


@bot.on_message(re.compile("^`disconnect"))
async def discon(message):
    if message.sender.name not in ADMINS:
        return
    await socket.disconnect()
    await message.reply("Disconnected")


@bot.on_message(re.compile("^`reload"))
async def reload(message):
    """reloads configuration"""
    global CONFIG, URL, ADMINS, TEXTTOSTRIP
    if message.sender.name not in ADMINS:
        return
    CONFIG = dotenv_values(".env")
    try:
        ADMINS = CONFIG.get("ADMINS", ADMINS)
        ADMINS = ADMINS.split(",")
    except Exception as err:
        logger.exception(err)
    TEXTTOSTRIP = CONFIG.get("TEXTTOSTRIP", TEXTTOSTRIP)
    URL = CONFIG.get("URL", URL)
    await message.reply("OK")


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
    except KeyboardInterrupt as err:
        logger.exception(err)
        logger.info("Caught keyboard interrupt. Canceling tasks...")
        tasks.cancel()
        loop.run_forever()
        tasks.exception()
    finally:
        loop.close()

"""
TODO
- [ ] OoP/Classes for bot and socket
- [ ] support listening to multiple sockets at once
    - [ ] track socket per channel
- [ ] smarter admin support
- [ ] requirements.txt support
"""
