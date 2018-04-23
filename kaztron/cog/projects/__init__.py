from .projects import ProjectsCog
from .query import init_db


def setup(bot):
    init_db()
    bot.add_cog(ProjectsCog(bot))
