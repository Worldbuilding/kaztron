import logging

import discord
from discord.ext import commands

from kaztron.utils.strings import count_words
from kaztron.utils.wizard import make_wizard, len_validator
from . import model as m, query as q

logger = logging.getLogger(__name__)


keys = ['title', 'genre', 'subgenre', 'type', 'pitch']
keys_optional = ['subgenre']

start_msg = "Let the server know what projects you're working on! Other members on the " \
            "server can look up any of your registered projects. To cancel this wizard, " \
            "type `.project cancel`."
start_edit_msg_fmt = "You are editing your current project, {0.title}. If you don't want to " \
                     "change a previous value, type `None` for that question. To cancel this " \
                     "wizard, type `.project cancel`."
end_msg = "Your project's been created! Other members can now look it up and find out what" \
              "you're up to!\n\nIf you'd like to re-run this wizard to make changes to your " \
              "project, use `.projects wizard`. You can also edit fields or add additional " \
              "info using the `.projects edit` series of commands. Do `.help projects edit` " \
              "for more information."


questions = {
    'title': "What is your project's title?",
    'genre': lambda: ("What genre is your project? Available genres: {}. "
                      "(You can specify a more specific sub-genre later.)"
                      ).format(', '.join(o.name for o in q.query_genres())),
    'subgenre': "What specific sub-genre is your project? Type `none` if you don't want to add"
                "a sub-genre..",
    'type': lambda: "What kind of project? Available types: {}."
                    .format(', '.join(o.name for o in q.query_project_types())),
    'pitch': "Give an elevator pitch (about 50 words) for your project!"
}


def pitch_validator(s: str):
    wc = count_words(s)
    if wc > m.Project.MAX_PITCH_WORDS:
        raise ValueError("Elevator pitch too long ({:d} words, max {:d})"
            .format(wc, m.Project.MAX_PITCH_WORDS))
    return s


validators = {
    'title': len_validator(m.Project.MAX_TITLE),
    'genre': q.get_genre,
    'subgenre': len_validator(m.Project.MAX_SHORT),
    'type': q.get_project_type,
    'pitch': pitch_validator,
    'description': len_validator(m.Project.MAX_FIELD)
}


ProjectWizard = make_wizard(keys, questions, validators, keys_optional)
