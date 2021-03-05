"""
Patches for discord.py v0.16.x.

These are all hacky as hell and I'm not proud of 'em.
"""

import functools
import logging
from types import MethodType
from enum import Enum

from discord.ext import commands


class Patches(Enum):
    smart_quotes = 0
    command_logging = 1
    everyone_filter = 2
    mobile_embeds = 3


def apply_patches(client: commands.Bot, excl=tuple()):
    """
    Apply all patches. See the Patches enum.

    :param client: Client to patch.
    :param excl: List of patches to exclude.
    :return:
    """
    if Patches.smart_quotes not in excl:
        patch_smart_quotes(client)
    if Patches.command_logging not in excl:
        patch_command_logging()
    if Patches.everyone_filter not in excl:
        patch_everyone_filter(client)
    if Patches.mobile_embeds not in excl:
        patch_mobile_embeds(client)


def patch_command_logging():
    """
    Patch to consistently log command invocations prior to running.

    We chose to use this instead of the "on_command" event because said event would be added to the
    event loop and consistently executed after the command itself has started or even completed,
    making the command log line rather less useful.
    """
    try:  # if already patched, return
        # noinspection PyProtectedMember
        _ = commands.Command._kt_command_logging_hack
        return
    except AttributeError:
        pass  # not already patched, carry on

    from kaztron.utils.logging import message_log_str

    cmd_logger = logging.getLogger("kaztron.commands")
    commands.Command._kt_old_invoke = commands.Command.invoke

    async def new_invoke(self, ctx):
        cmd_logger.info("{!s}: {}".format(self, message_log_str(ctx.message)))
        await self._kt_old_invoke(ctx)

    commands.Command.invoke = new_invoke
    commands.Command._kt_command_logging_hack = True


def patch_everyone_filter(client: commands.Bot):
    """
    Patch to prevent @everyone and @here from being sent if not explicitly desired.

    This allows the bot to maintain the @everyone permission for cases where it's used
    intentionally, while avoiding most accidental uses or possible privilege-escalation
    vulnerabilities where KazTron makes use of user inputs.

    This patch is not quite as transparent/backwards-compatible as others, as it adds an
    `allow_everyone` parameter to the method.
    """
    old_send_message = client.send_message
    conversion_map = {
        '@everyone': '@\u200beveryone',  # alternative: '@\u0435v\u0435ry\u03bfn\u0435'
        '@here': '@\u200bhere',  # alternative: '@h\u0435r\u0435'
    }

    @functools.wraps(client.send_message)
    async def new_send_message(self, dest, content=None, *args, allow_everyone=False, **kwargs):
        if content is not None:
            content = str(content)
            if not allow_everyone:
                for f, r in conversion_map.items():
                    content = content.replace(f, r)
        return await old_send_message(dest, content, *args, **kwargs)
    # noinspection PyArgumentList
    client.send_message = MethodType(new_send_message, client)


def patch_smart_quotes(client: commands.Bot):
    """
    Patch to convert smart quotes to ASCII quotes when processing commands in discord.py

    Because iOS by default is stupid and inserts smart quotes, and not everyone configures their
    mobile device to be SSH-friendly. WTF, Apple, way to ruin basic input expectations across your
    *entire* OS.
    """
    old_process_commands = client.process_commands
    conversion_map = {
        '\u00ab': '"',
        '\u00bb': '"',
        '\u2018': '\'',
        '\u2019': '\'',
        '\u201a': '\'',
        '\u201b': '\'',
        '\u201c': '"',
        '\u201d': '"',
        '\u201e': '"',
        '\u201f': '"',
        '\u2039': '\'',
        '\u203a': '\'',
        '\u2042': '"'
    }

    @functools.wraps(client.process_commands)
    async def new_process_commands(self, message, *args, **kwargs):
        for f, r in conversion_map.items():
            message.content = message.content.replace(f, r)
        return await old_process_commands(message, *args, **kwargs)
    # noinspection PyArgumentList
    client.process_commands = MethodType(new_process_commands, client)


def patch_mobile_embeds(client: commands.Bot):
    """
    Patch to fix a stupid, stupid Android!Discord bug where it doesn't consider Embed fields when
    calculating the width of the embed. Yup. Sigh.

    It results in a minimum-width embed that looks like a grey and coloured vertical line, which
    scrolls forever because all of the field contents are wrapping like hell.
    """
    from discord.embeds import Embed
    old_send_message = client.send_message

    @functools.wraps(client.send_message)
    async def new_send_message(self, dest, content=None, *args, **kwargs):
        e = kwargs.get('embed', None)

        def min_len(x):
            return x and x is not Embed.Empty and len(x) >= 80
        hr = r'_' * 80
        hr_ts = r'_' * 60

        if e is not None and e.fields and not (min_len(e.description) or min_len(e.author.name) or
                                               min_len(e.title)):
            if e.footer is None or e.footer.text == Embed.Empty:
                e.set_footer(text=hr if e.timestamp is Embed.Empty else hr_ts)
            elif hr not in e.footer.text:
                e.set_footer(text=hr + '\n' + e.footer.text)
        return await old_send_message(dest, content, *args, **kwargs)
    # noinspection PyArgumentList
    client.send_message = MethodType(new_send_message, client)

    # old_set_footer = EmbedSplitter.set_footer
    #
    # @functools.wraps(EmbedSplitter.set_footer)
    # def new_set_footer(self, *, text: str, **kwargs):
    #     if not self.suppress_patch_mobile:
    #         if text == Embed.Empty:
    #             text = '_'*80
    #         else:
    #             text = (r'_'*80) + '\n' + text
    #     old_set_footer(self, text=text, **kwargs)
    #
    # old_es_init = EmbedSplitter.__init__
    #
    # @functools.wraps(EmbedSplitter.__init__)
    # def new_es_init(self, *args, **kwargs):
    #     old_es_init(self, *args, **kwargs)
    #     self.suppress_patch_mobile = False
    #     self.set_footer(text='')
    #
    # EmbedSplitter.__init__ = new_es_init
    # EmbedSplitter.set_footer = new_set_footer


