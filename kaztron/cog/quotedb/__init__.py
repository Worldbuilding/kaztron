from .quotecog import QuoteCog
from .controller import init_db


def setup(bot):
    init_db()
    bot.add_cog(QuoteCog(bot))
