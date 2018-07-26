from discord.ext import commands

from kaztron import KazCog
from kaztron.utils.embeds import EmbedSplitter


class TestCog(KazCog):
    @commands.command(pass_context=True)
    async def embedsplitter(self, ctx):
        es = EmbedSplitter(auto_truncate=True, title="asdfjkl ", description="short and stout ")
        es.set_author(name='ABCMan1 ', url='https://google.com')

        for i in range(10):
            es.add_field_no_break(name=str(i) + " A", value="A")
            es.add_field_no_break(name=str(i) + " B", value="B")
            es.add_field(name=str(i) + " C", value="CCCC", inline=False)

        for i in range(10):
            es.add_field_no_break(name=str(i) + " A", value="A")
            es.add_field_no_break(name=str(i) + " B", value="B")
            es.add_field(name=str(i) + " C", value="CCC "*256+'DDD '*32, inline=False)

        embeds = es.finalize()
        self.bot.say(str(len(embeds)))
        for em in embeds:
            await self.bot.say(embed=em)


def setup(bot):
    bot.add_cog(TestCog(bot))
