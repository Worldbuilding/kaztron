import logging
from typing import Sequence

import discord
from discord.ext import commands

from kaztron.theme import solarized
from . import model as m, query as q
from kaztron.utils.discord import extract_role_id, get_named_role, user_mention, role_mention

logger = logging.getLogger(__name__)


__all__ = ['get_role', 'update_user_roles',
           'update_project_message', 'delete_project_message', 'get_project_embed']

EMBED_COLOUR = solarized.orange


def get_project_embed(project: m.Project, user_info=True, desc=True) -> discord.Embed:
    em = discord.Embed(
        title=project.title,
        description='by {}\n\n{}'.format(user_mention(project.user.discord_id), project.pitch),
        color=EMBED_COLOUR
    )
    em.add_field(name='Genre',
        value='{0.genre.name} - {0.subgenre}'.format(project) if project.subgenre
              else '{0.genre.name}'.format(project))
    em.add_field(name='Type', value=project.type.name)
    if project.follow_role_id:
        em.add_field(name='Follow role', value=role_mention(project.follow_role_id))
    if project.url:
        em.add_field(name='More info', value="[More info]({})".format(project.url))
    if desc and project.description:
        em.add_field(name='Description', value=project.description)

    # user info
    if user_info:
        user = project.user
        if user.about:
            msg = "{} is {}".format(user_mention(user.discord_id), user.about)
        else:
            msg = "*(no bio)*"

        em.add_field(name="About the author", value=msg, inline=False)

        if user.genre:
            em.add_field(name="Genre", value=user.genre.name)
        if user.type:
            em.add_field(name="Type", value=user.type.name)
        if user.url:
            em.add_field(name='More info', value="[More info]({})".format(user.url))
    return em


def get_role(server: discord.Server, role_arg: str) -> discord.Role:
    """
    Get a role from a passed argument (name, mention or ID).
    :return:
    """
    try:
        role_id = extract_role_id(role_arg)
    except discord.InvalidArgument:  # no ID, treat as a role name
        try:
            role = get_named_role(server, role_arg)  # type: discord.Role
        except discord.InvalidArgument:
            logger.warning("Cannot find role {!r} as name or ID".format(role_arg))
            role = None
    else:
        logger.debug("Found role ID in {!r}".format(role_arg))
        role = discord.utils.get(server.roles, id=role_id)  # type: discord.Role

    if role is None:
        raise commands.BadArgument('No such role: {}'.format(role))
    return role


async def update_user_roles(bot: discord.Client, server: discord.Server, users: Sequence[m.User]):
    # noinspection PyTypeChecker
    role_ids = [o.role_id for o in q.query_genres() + q.query_project_types()]
    project_roles = set(get_role(server, role_id) for role_id in role_ids if role_id is not None)

    for u in users:
        member = server.get_member(u.discord_id)
        desired_roles = set()
        for taxon in {u.genre, u.type} - {None}:
            if taxon.role_id is not None:
                desired_roles.add(get_role(server, taxon.role_id))
        new_roles = (set(member.roles) - project_roles) | desired_roles
        await bot.replace_roles(member, *new_roles)


async def update_project_message(bot: discord.Client, dest: discord.Channel, project: m.Project):
    """
    Send or update a project's Discord message entry.

    Should be executed in a :func:`~q.transaction()` context, as the ``project`` object may be
    modified by this function.
    """
    new_embed = get_project_embed(project, user_info=False, desc=False)

    # check for/find the message
    whois_msg = None
    try:
        if project.whois_message_id:
            whois_msg = await bot.get_message(dest, project.whois_message_id)
    except discord.NotFound:
        pass

    # edit or post the message
    if whois_msg:
        await bot.edit_message(whois_msg, embed=new_embed)
    else:  # no message exists yet
        new_msg = await bot.send_message(dest, embed=new_embed)
        project.whois_message_id = new_msg.id


async def delete_project_message(bot: discord.Client, dest: discord.Channel, project: m.Project):
    try:
        if project.whois_message_id:
            whois_msg = await bot.get_message(dest, project.whois_message_id)
            logger.info("Deleting project whois message (for project {!r})".format(project))
            await bot.delete_message(whois_msg)
            project.whois_message_id = None
    except discord.NotFound:
        logger.warning("Cannot delete project whois message: not found (for project {!r})"
            .format(project))
        logger.warning("Removing whois message ID (for project {!r})".format(project))
        project.whois_message_id = None
        pass
