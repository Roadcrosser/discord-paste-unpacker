import discord
import aiohttp
import traceback
import sys
import re
import json

with open("config.json", encoding="utf8") as o:
    config = json.loads(o.read())

bot = discord.Client()


@bot.event
async def on_ready():
    bot.session = aiohttp.ClientSession()
    print(f"Running as {bot.user.name}#{bot.user.discriminator} ({bot.user.id})")


def get_url_match(url):
    for reg in txt_url_regexes:
        match = reg[0].match(url)
        if match:
            return match, reg
    return None, None


async def unpack_content(match, reg):
    errored = False
    unpacked_content = None
    try:
        unpacked_content = await reg[1](match)
    except ValueError as e:
        print(
            "".join(traceback.TracebackException.from_exception(e).format()),
            file=sys.stderr,
        )
        errored = True
        unpacked_content = f"```\n{e}\n```"

    return unpacked_content, errored


@bot.event
async def on_message(message):
    if (
        message.author.bot
        or (not message.channel.permissions_for(message.guild.me).send_messages)
        or (not message.content)
        or (not message.content.startswith(config["prefix"]))
    ):
        return

    content = message.content[len(config["prefix"]) :]
    if not content.strip():
        return

    content = content.split()

    if content[0].lower() in ("extract", "unpack"):
        print(
            f"{message.guild.name}#{message.channel.name} {message.author.name}: {message.content}"
        )
        content_url = None

        if message.attachments:
            content_url = message.attachments[0].url
        elif len(content) > 1:
            content_url = content[1]

        if not content_url:
            return

        content_url = content_url.strip("<>")

        unpacked_content = None
        escape_markdown = True

        match, reg = get_url_match(content_url)

        if match:
            unpacked_content, errored = await unpack_content(match, reg)
            escape_markdown = not errored
        elif content_url.startswith(("http://", "https://")):
            # This whole bit is for resolving URL shorteners just why
            resp, text = await get_url_response(content_url)
            match, reg = get_url_match(str(resp.url))
            if match:
                if reg[1] == unpack_url_file:
                    unpacked_content = text
                else:
                    unpacked_content, errored = await unpack_content(match, reg)
                    escape_markdown = not errored

        character_limit = config["normal_user_charlimit"]
        if message.channel.permissions_for(message.author).manage_messages:
            character_limit = config["manage_message_user_charlimit"]

        # Process the message here
        unpacked_content = unpacked_content[:character_limit]
        if escape_markdown:
            unpacked_content = discord.utils.escape_markdown(unpacked_content)
        unpacked_content = discord.utils.escape_mentions(unpacked_content)

        await send_message(message.channel, unpacked_content)


async def get_url_response(url):
    async with bot.session.get(url) as r:
        resp = r
        text = await r.text()
        if r.status != 200:
            raise ValueError(f"Error: {r.status}")
    return resp, text


async def get_url_contents(url):
    _, text = await get_url_response(url)
    return text


async def unpack_url_file(match):
    return await get_url_contents(match.groups()[0])


async def unpack_pastebin(match):
    groups = match.groups()
    url = f"{groups[0]}raw/{groups[1]}"
    return await get_url_contents(url)


async def unpack_gist(match):
    url = f"https://api.github.com/gists/{match.groups()[0]}"
    async with bot.session.get(url) as r:
        data = await r.json()
        if r.status != 200:
            raise ValueError(data)

    content = "\n\n".join([d["content"] for d in data["files"].values()])

    return content


async def unpack_github(match):
    groups = match.groups()
    url = f"https://raw.githubusercontent.com/{groups[0]}{groups[1]}"
    return await get_url_contents(url)


txt_url_regexes = [
    (
        re.compile(r"^https?:\/\/gist\.github\.com\/.+\/([a-f0-9]+)$"),
        unpack_gist,
    ),  # gist
    (
        re.compile(r"^(https?:\/\/(?:h|p)astebin\.com\/)(\w+)$"),
        unpack_pastebin,
    ),  # pastebin
    (
        re.compile(r"^(https?:\/\/(?:h|p)astebin\.com\/raw\/\w+)$"),
        unpack_url_file,
    ),  # raw pastebin
    (re.compile(r"^https?:\/\/github\.com\/(.+\/.+)\/blob(\/.+\/.+)$"), unpack_github),
    (
        re.compile(r"^(https?:\/\/raw\.githubusercontent\.com\/.+\/.+\/.+\/.+)$"),
        unpack_url_file,
    ),  # raw github
    (re.compile(r"^(https?:\/\/.+\.txt)$"), unpack_url_file),  # other url file thing
]


async def send_message(dest, content):
    msg = None
    try:
        if len(content) > 2000:
            await dest.send(content[:2000])
            msg = await send_message(dest, content[2000:])
        else:
            msg = await dest.send(content)
    except Exception as e:
        await dest.send("```\n" + str(e) + "\n```")
        print(
            f"Failed to send message to {dest.guild.name} ({dest.guild.id}): {content}",
            file=sys.stderr,
        )
        print(
            "".join(traceback.TracebackException.from_exception(e).format()),
            file=sys.stderr,
        )
    return msg


bot.run(config["token"])

