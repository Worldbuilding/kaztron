from .sprint import WritingSprint


def setup(bot):
    bot.add_cog(WritingSprint(bot))
