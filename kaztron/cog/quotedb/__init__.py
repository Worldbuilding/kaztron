from kaztron.cog.quotedb.quotecog import QuoteCog
from kaztron.cog.quotedb.controller import init_db


def setup(bot):
    init_db()
    bot.add_cog(QuoteCog(bot))
