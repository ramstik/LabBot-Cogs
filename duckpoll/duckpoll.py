import time
from io import BytesIO
from typing import Mapping, Union

import aiohttp
import discord
from discord.ext import tasks
from redbot.core import Config, commands


class DuckPollCog(commands.Cog):
    DUCK_IMAGE_URL = "https://i.imgur.com/xjzCAiR.jpg"
    EMOJIS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    DEFAULT_SETTINGS = {"messages": []}  # {guild_id: int, channel_id: int, message_id: int, created_at: float}

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=377212919068229633)
        self.config.register_global(**self.DEFAULT_SETTINGS)
        self.cleanup_messages.start()

    # Events

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: Union[discord.User, discord.Member]):
        """Enforces 1 reaction per user on duck polls"""
        if user.bot or not reaction.message.guild:
            # User is bot or message not in guild
            return

        message = reaction.message

        async with self.config.messages() as messages:
            if not list(
                filter(
                    lambda m: all(
                        (m["guild_id"] == message.guild.id),
                        (m["channel_id"] == message.channel.id),
                        (m["message_id"] == message.id),
                    ),
                    messages,
                )
            ):
                # It's not a duck poll message
                return

        if str(reaction.emoji) not in self.EMOJIS:
            # Only emojis from self.EMOJIS are allowed
            # Remove this emoji from the reactions
            return await message.clear_reaction(reaction.emoji)

        if len([x for y in [await r.users().flatten() for r in message.reactions] for x in y if x.id == user.id]) > 1:
            # User has reacted to the message more than once
            # Remove this reaction
            await message.remove_reaction(reaction.emoji, user)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Removes duck poll messages from the database if they've been deleted"""
        if not message.guild or not message.author.bot:
            # Message is in a DM or sent by a regular user
            return

        async with self.config.messages() as messages:
            try:
                (stored_message,) = filter(
                    lambda m: all(
                        m["guild_id"] == message.guild.id, m["channel_id"] == message.channel.id, m["message_id"] == message.id
                    ),
                    messages,
                )
            except ValueError:
                # Message is not a duck poll
                return
            else:
                messages.remove(stored_message)

    # Tasks

    @tasks.loop(seconds=60)  # Every minute
    async def cleanup_messages(self):
        """Removes all messages from the database if they're older than 24 hours"""
        async with self.config.messages() as messages:
            [
                (self.bot.create_task(self.send_stats(m)), messages.remove(m))
                for m in filter(lambda m: m["created_at"] < (time.time() - (60 * 60 * 24)), messages)
            ]

    # Command groups

    @commands.group("duck", invoke_without_command=True)
    async def duck(self, ctx: commands.Context):
        """Check in on your members and see how they're doing!"""
        if ctx.invoked_subcommand:
            return

        message = await ctx.send("On a rubber duck scale, how's your day going?", file=await self.get_duck_image())
        for emoji in self.EMOJIS:
            await message.add_reaction(emoji)

    # Commands

    @duck.command("stats")
    async def duck_stats(self, ctx):
        """See the stats of the last duck poll in this channel"""
        async with self.config.messages() as messages:
            channel_duck_polls = sorted(
                filter(lambda m: all(m["guild_id"] == ctx.guild.id, m["channel_id"] == ctx.channel.id), messages),
                key=lambda m: m["created_at"],
            )
            if not channel_duck_polls:
                return await ctx.send("No existing duck polls for this channel found")

            poll = channel_duck_polls[0]
            try:
                message = await ctx.channel.fetch_message(poll["message_id"])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return await ctx.send("No existing duck polls for this channel found")
            else:
                stats = await self.get_stats(message)
                ctx = await self.bot.get_context(message)
                embed = await self.make_stats_embed(ctx, stats, poll)
                await ctx.send(embed=embed)

    # Utility methods

    async def send_stats(self, message: dict, return_error: bool = False):
        """Send stats to channel"""
        guild = self.bot.get_guild(message["guild_id"])
        if not guild:
            # Couldn't find guild
            return

        channel = guild.get_channel(message["channel_id"])
        if not channel:
            # Couldn't find channel
            return

        try:
            message = await channel.fetch_message(message["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            # Couldn't find message
            if return_error:
                await channel.send("No existing duck polls for this channel found")
        else:
            ctx = await self.bot.get_context(message)
            stats = await self.get_stats(message)
            embed = await self.make_stats_embed(ctx, stats, message)
            await channel.send(embed=embed)

    async def get_duck_image(self) -> discord.File:
        """Fetches the duck image for usage in a message"""
        async with aiohttp.request("GET", self.DUCK_IMAGE_URL) as response:
            content = await response.read()
            return discord.File(BytesIO(content), filename="duck.jpg")

    async def get_stats(self, message: discord.Message) -> Mapping[str, int]:
        """Retrieves the poll stats for a duck poll message
        In the format {1️⃣: int, 2️⃣: int, ...}"""
        reactions = {str(r.emoji): r.count - 1 for r in message.reactions if str(r.emoji) in self.EMOJIS}
        return {emoji: reactions.get(emoji, 0) for emoji in self.EMOJIS}

    async def make_stats_embed(self, ctx: commands.Context, stats: Mapping[str, int], data: dict) -> discord.Embed:
        """Generate embed for duck poll stats"""
        sum_of_votes = sum(stats.values())
        embed = discord.Embed(
            title="Duck poll stats",
            colour=await ctx.embed_colour(),
            description=f"[Jump to message](https://discord.com/channels/{data['guild_id']}/{data['channel_id']}/{data['message_id']})"
        )
        list(
            map(
                lambda v: embed.add_field(
                    name=f"{v[0]} - {v[1]}",
                    value="".join("█" for _ in range(round(v[1] / sum_of_votes * 10))).ljust(10, "░")
                    + f" {round(v[1] / sum_of_votes * 100)}%",
                    inline=False,
                ),
                stats.items(),
            )
        )
        return embed
