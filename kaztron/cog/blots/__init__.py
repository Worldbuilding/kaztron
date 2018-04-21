from .checkin import CheckInManager
from .badges import BadgeManager
from .controller import init_db


def setup(bot):
    init_db()
    bot.add_cog(CheckInManager(bot))
    bot.add_cog(BadgeManager(bot))
