from kaztron.cog.modnotes.cog import ModNotes
from kaztron.cog.modnotes.controller import init_db


def setup(bot):
    init_db()
    bot.add_cog(ModNotes(bot))
