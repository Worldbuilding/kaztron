from .modnotes import ModNotes
from .controller import init_db


def setup(bot):
    init_db()
    bot.add_cog(ModNotes(bot))
