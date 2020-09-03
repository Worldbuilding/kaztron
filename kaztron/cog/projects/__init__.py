def setup(bot):
    from .projects import ProjectsManager
    from .query import init_db
    init_db()
    bot.add_cog(ProjectsManager(bot))
