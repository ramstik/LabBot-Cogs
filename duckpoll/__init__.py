from .duckpoll import DuckPollCog


def setup(bot):
    bot.add_cog(DuckPollCog(bot))
