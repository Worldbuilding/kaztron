import discord
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

    @commands.command(pass_context=True)
    async def message_splitter(self, ctx: commands.Context):
        lines = []
        for i in range(50):
            lines.append('{:d}. The quick brown fox jumped over the lazy dog.'.format(i))
        full_text = '\n'.join(lines)
        await self.send_message(ctx.message.channel, full_text, split='line')
        await self.send_message(ctx.message.channel, full_text, split='word')
        try:
            await self.send_message(ctx.message.channel, full_text, auto_split=False)
        except discord.HTTPException as e:
            await self.send_message(ctx.message.channel, "Got expected error: " + str(e))
        else:
            await self.send_message(ctx.message.channel, "Fail: expected HTTPException")

    @commands.command(pass_context=True)
    async def mixed_splitter(self, ctx: commands.Context):
        lines = []
        for i in range(50):
            lines.append('{:d}. The quick brown fox jumped over the lazy dog.'.format(i))
        full_text = '\n'.join(lines)

        es = EmbedSplitter(auto_truncate=True, title="The Title", description="A Short Title")
        for i in range(10):
            es.add_field_no_break(name=str(i) + " A", value="A")
            es.add_field_no_break(name=str(i) + " B", value="B")
            es.add_field(name=str(i) + " C", value="CCC "*256+'DDD '*32, inline=False)

        await self.send_message(ctx.message.channel, full_text, embed=es, split='line')


def setup(bot):
    bot.add_cog(TestCog(bot))
