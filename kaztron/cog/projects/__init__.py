def setup(bot):
    from .projects import ProjectsCog
    from .query import init_db
    init_db()
    bot.add_cog(ProjectsCog(bot))
