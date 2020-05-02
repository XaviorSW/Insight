from InsightSubsystems.Cache.CacheEndpoint.AbstractEndpoint import AbstractEndpoint
import discord
from discord.embeds import EmptyEmbed
from InsightUtilities.StaticHelpers import *
from datetime import datetime
from functools import partial


class AbstractEmbedEndpoint(AbstractEndpoint):
    def default_color(self) -> discord.Color:
        return discord.Color(659493)

    def make_embed(self, d: dict) -> discord.Embed:
        e = discord.Embed.from_dict(d)
        return e

    async def get(self, **kwargs) -> discord.Embed:
        response = await super().get(**kwargs)
        return await self.loop.run_in_executor(self.thread_pool, partial(self.make_embed, response))
