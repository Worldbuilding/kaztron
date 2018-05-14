import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, Union

import discord
from discord.ext import commands

from kaztron.utils.logging import message_log_str
from kaztron.utils.strings import count_words
from kaztron.utils.wizard import make_wizard, len_validator
from . import model as m, query as q

logger = logging.getLogger(__name__)


keys = ['title', 'genre', 'subgenre', 'type', 'pitch']
keys_optional = ['subgenre']

start_msg = "**New Project Wizard**\n\n" \
            "Let the server know what projects you're working on! Other members on the " \
            "server can look up any of your registered projects. To cancel this wizard, " \
            "type `.project cancel`."
start_edit_msg_fmt = "**Edit Project Wizard**\n\n" \
                     "You are editing your current project, {0.title}. If you don't want to " \
                     "change a previous value, type `skip` for that question. To cancel this " \
                     "wizard, type `.project cancel`."
end_msg = "Your project is set up! Other members can now look it up and find out what" \
              "you're up to!\n\nIf you'd like to re-run this wizard to make changes to your " \
              "project, use `.project wizard`. You can also edit fields or add additional " \
              "info using the `.project set` series of commands. Do `.help projects set` " \
              "for more information."


questions = {
    'title': "What is your project's title?",
    'genre': lambda: ("What genre is your project? Available genres: {}. "
                      "(You can specify a more specific sub-genre later.)"
                      ).format(', '.join(o.name for o in q.query_genres())),
    'subgenre': "What specific sub-genre is your project? Type `none` if you don't want to add "
                "a sub-genre.",
    'type': lambda: "What kind of project? Available types: {}."
                    .format(', '.join(o.name for o in q.query_project_types())),
    'pitch': "Give an elevator pitch (about 50 words) for your project!"
}

aboutme_keys = ['bio', 'genre', 'type', 'url']
aboutme_start_msg = "**Author Info Wizard\n\n" \
                    "Set up your public author/user profile! Anyone can look this information up. "\
                    "If you don't want to change the old value, type `skip`. " \
                    "To cancel this wizard, type `.project cancel`."

aboutme_end_msg = "Your profile is set up! If you'd like to re-run this wizard to make " \
                  "changes to your profile, use `.project aboutme`."

aboutme_questions = {
    'bio': "Write a short bio about yourself (~50 words) by "
           "continuing this sentence: \"The author is ...\"\n\n(You can also type `blank`.)",
    'genre': lambda: "What genre do you prefer? Available genres: {}."
                     .format(', '.join(o.name for o in q.query_genres())),
    'type': lambda: ("What kind of work do you primarily do? Available types: {}."
                     ).format(', '.join(o.name for o in q.query_project_types())),
    'url': "Do you have a website or webpage for more info about you? Enter the URL, or `blank`."
}


def pitch_validator(s: str):
    wc = count_words(s)
    if wc > m.Project.MAX_PITCH_WORDS:
        raise ValueError("Elevator pitch too long ({:d} words, max {:d})"
            .format(wc, m.Project.MAX_PITCH_WORDS))
    return s


def bio_validator(s: str):
    if s.lower() == 'blank':
        return ''

    wc = count_words(s)
    if wc > m.User.MAX_ABOUT_WORDS:
        raise ValueError("Bio too long ({:d} words, max {:d})"
            .format(wc, m.User.MAX_ABOUT_WORDS))
    return s


def url_validator(s: str):
    if s.lower() == 'blank':
        return ''
    else:
        return len_validator(m.Project.MAX_TITLE)


validators = {
    'title': len_validator(m.Project.MAX_TITLE),
    'genre': lambda x: q.get_genre(x),
    'subgenre': len_validator(m.Project.MAX_SHORT),
    'type': lambda x: q.get_project_type(x),
    'pitch': pitch_validator,
    'description': len_validator(m.Project.MAX_FIELD),
    'url': url_validator,
    'bio': bio_validator,
}

serializers = {
    'genre': lambda x: x.name,
    'type': lambda x: x.name
}


ProjectWizard = make_wizard(keys, questions, validators, serializers, keys_optional)
AuthorWizard = make_wizard(aboutme_keys, aboutme_questions, validators, serializers, aboutme_keys)

UserWizardMap = Dict[str, ProjectWizard]


class WizardManager:
    @classmethod
    def from_dict(cls, bot: commands.Bot, server: discord.Server, data: dict, timeout=None):
        obj = cls(bot, server, timeout)
        for uid, d in data.get('new', {}).items():
            try:
                obj.wizards['new'][uid] = ProjectWizard.from_dict(d)
            except ValueError:
                pass

        obj.edit_wizards = {}
        for uid, d in data.get('edit', {}).items():
            try:
                obj.wizards['edit'][uid] = ProjectWizard.from_dict(d)
                obj.wizards['edit'][uid].opts = ProjectWizard.question_keys
            except ValueError:
                pass
        return obj

    def __init__(self, bot: commands.Bot, server: discord.Server, timeout: int=None):
        """

        :param bot:
        :param server:
        :param timeout: in seconds, time before a wizard is timed out
        """
        self.bot = bot
        self.server = server
        self.wizards = {
            'new': {},
            'edit': {},
            'author': {},
        }
        self.timeout = timedelta(seconds=timeout)

    def has_open_wizard(self, member: discord.Member):
        return any(member.id in w for w in self.wizards.values())

    def get_wizard_for(self, member: discord.Member)\
            -> Tuple[str, Union[ProjectWizard, AuthorWizard]]:
        for name, uw_map in self.wizards.items():
            try:
                if uw_map[member.id] is None:
                    raise KeyError
                return name, uw_map[member.id]
            except KeyError:
                continue
        else:
            raise KeyError("Member {} does not have an active wizard".format(member))

    async def send_question(self, member: discord.Member):
        await self.purge()
        await self.bot.send_message(member, self.get_wizard_for(member)[1].question)

    async def create_new_wizard(self, member: discord.Member, timestamp: datetime):
        await self.purge()
        if self.has_open_wizard(member):
            raise commands.CommandError("You already have an ongoing wizard!")

        logger.info("Starting 'new' wizard for {}".format(member))
        self.wizards['new'][member.id] = ProjectWizard(member.id, timestamp)

        try:
            await self.bot.send_message(member, start_msg)
            await self.send_question(member)
        except Exception:
            self.cancel_wizards(member)
            raise

    async def create_edit_wizard(self,
                                 member: discord.Member, timestamp: datetime, proj: m.Project):
        await self.purge()
        if self.has_open_wizard(member):
            raise commands.CommandError("You already have an ongoing wizard!")

        logger.info("Starting 'edit' wizard for for {}".format(member))
        w = ProjectWizard(member.id, timestamp)
        w.opts = ProjectWizard.question_keys
        self.wizards['edit'][member.id] = w

        try:
            await self.bot.send_message(member, start_edit_msg_fmt.format(proj))
            await self.send_question(member)
        except Exception:
            self.cancel_wizards(member)
            raise

    async def create_author_wizard(self, member: discord.Member, timestamp: datetime):
        await self.purge()
        if self.has_open_wizard(member):
            raise commands.CommandError("You already have an ongoing wizard!")

        logger.info("Starting 'author' wizard for {}".format(member))
        w = AuthorWizard(member.id, timestamp)
        self.wizards['author'][member.id] = w

        try:
            await self.bot.send_message(member, aboutme_start_msg)
            await self.send_question(member)
        except Exception:
            self.cancel_wizards(member)
            raise

    async def process_answer(self, message: discord.Message):
        await self.purge()
        wiz_name, wizard = self.get_wizard_for(message.author)

        logger.info("Processing '{}' wizard answer for {}".format(wiz_name, message.author))
        logger.debug(message_log_str(message))

        wizard.answer(message.content)

    async def close_wizard(self, member: discord.Member) -> Tuple[str, ProjectWizard]:
        await self.purge()
        wiz_name, wizard = self.get_wizard_for(member)
        if wizard.is_done:
            logger.info("Closing '{}' wizard for {}".format(wiz_name, member))
            del self.wizards[wiz_name][member.id]
            await self.bot.send_message(
                member, end_msg if wiz_name != 'author' else aboutme_end_msg
            )
            return wiz_name, wizard
        else:
            raise KeyError("Wizard for user {} not completed yet".format(member))

    async def cancel_wizards(self, member: discord.Member):
        await self.purge()
        for name, user_wizard_map in self.wizards.items():
            try:
                del user_wizard_map[member.id]
            except KeyError:
                pass  # no open wizard of this kind
            else:
                logger.info("Cancelled {} project wizard for user {}".format(name, member))
                if name == 'new':
                    await self.bot.send_message(member, "New project has been cancelled.")
                elif name == 'edit':
                    await self.bot.send_message(member, "Editing your project has been cancelled.")
                else:
                    await self.bot.send_message(member, "Wizard has been cancelled (generic msg).")

    async def purge(self):
        """ Purge any timed-out wizards. """
        now = datetime.utcnow()
        for name, user_wizard_map in self.wizards.items():
            delete_keys = []
            for uid, wizard in user_wizard_map.items():
                if now - wizard.timestamp >= self.timeout:
                    delete_keys.append(uid)
            for uid in delete_keys:
                member = self.server.get_member(uid)
                logger.info("{} wizard for {!r} timed out"
                    .format(name.capitalize(), member if member else uid))
                del user_wizard_map[uid]
                if name == 'new':
                    await self.bot.send_message(member,
                        "New project wizard has timed out. You will need to restart the wizard "
                        "with `.project new`.")
                elif name == 'edit':
                    await self.bot.send_message(member,
                        "Editing your project has timed out. You will need to restart the wizard "
                        "with `.project wizard`.")
                else:
                    await self.bot.send_message(member, "Wizard has timed out (generic msg).")

    def to_dict(self) -> dict:
        ret = {}
        for name, wiz_map in self.wizards.items():
            ret[name] = {uid: wiz.to_dict() for uid, wiz in wiz_map.items()}
        return ret
