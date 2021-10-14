from redbot.core.bot import Red

from .naughty import NaughtyCog


def setup(bot: Red):
    bot.add_cog(NaughtyCog(bot))
