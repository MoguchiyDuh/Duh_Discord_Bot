from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import BaseCog, channel_allowed
from bot.services.channels import CATEGORY_TEMP, VOICE_HUB

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TempChannelInfo:
    owner_id: int
    guild_id: int


class TempChannels(BaseCog, commands.GroupCog, name="temp_channels"):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)
        self.temp_channels: dict[int, TempChannelInfo] = {}

    async def cog_unload(self) -> None:
        for channel_id in list(self.temp_channels):
            info = self.temp_channels.pop(channel_id, None)
            if info is None:
                continue
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                guild = self.bot.get_guild(info.guild_id)
                if guild is None:
                    continue
                with contextlib.suppress(discord.HTTPException):
                    channel = await guild.fetch_channel(channel_id)
            if isinstance(channel, discord.abc.GuildChannel):
                with contextlib.suppress(discord.HTTPException):
                    await channel.delete(reason="Cog unload cleanup")

    async def _verify_owner(
        self, interaction: discord.Interaction
    ) -> discord.VoiceChannel | None:
        voice = interaction.user.voice if isinstance(interaction.user, discord.Member) else None
        if not voice or not voice.channel:
            await interaction.response.send_message(
                "❌ You must be in a voice channel", ephemeral=True
            )
            return None
        if not isinstance(voice.channel, discord.VoiceChannel):
            await interaction.response.send_message(
                "❌ You're not in a temporary channel", ephemeral=True
            )
            return None

        info = self.temp_channels.get(voice.channel.id)
        if not info:
            await interaction.response.send_message(
                "❌ You're not in a temporary channel", ephemeral=True
            )
            return None
        if info.owner_id != interaction.user.id:
            await interaction.response.send_message("❌ You don't own this channel", ephemeral=True)
            return None
        return voice.channel

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if after.channel and after.channel.name == VOICE_HUB:
            if self.bot.channels:
                await self.bot.channels.ensure(member.guild)

            category = discord.utils.get(member.guild.categories, name=CATEGORY_TEMP)
            if category is None:
                return
            try:
                temp_channel = await category.create_voice_channel(
                    name=f"{member.display_name}'s Room", user_limit=4
                )
                await member.move_to(temp_channel)
                self.temp_channels[temp_channel.id] = TempChannelInfo(
                    owner_id=member.id, guild_id=member.guild.id
                )
                logger.info("Created temp channel for %s", member.name)
            except discord.HTTPException:
                logger.exception("Failed to create temp channel in %s", member.guild.name)

        if (
            before.channel
            and before.channel.id in self.temp_channels
            and len(before.channel.members) == 0
        ):
            self.temp_channels.pop(before.channel.id, None)
            try:
                await before.channel.delete()
                logger.info("Deleted empty temp channel %s", before.channel.name)
            except discord.HTTPException:
                logger.exception("Failed to delete temp channel %s", before.channel.name)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        self.temp_channels.pop(channel.id, None)

    @app_commands.command(name="lock", description="🔒 Lock your temporary channel")
    @channel_allowed(__file__)
    async def lock(self, interaction: discord.Interaction) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        await channel.set_permissions(
            interaction.guild.default_role,
            connect=False,
            reason=f"Locked by {interaction.user.name}",
        )
        await interaction.response.send_message(f"🔒 {channel.mention} is now locked", ephemeral=True)

    @app_commands.command(name="unlock", description="🔓 Unlock your temporary channel")
    @channel_allowed(__file__)
    async def unlock(self, interaction: discord.Interaction) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        await channel.set_permissions(
            interaction.guild.default_role,
            connect=True,
            reason=f"Unlocked by {interaction.user.name}",
        )
        await interaction.response.send_message(
            f"🔓 {channel.mention} is now unlocked", ephemeral=True
        )

    @app_commands.command(name="limit", description="👥 Set user limit (0-99)")
    @app_commands.describe(limit="Max number of users (0 for no limit)")
    @channel_allowed(__file__)
    async def limit(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]
    ) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        await channel.edit(user_limit=limit)
        message = f"👥 User limit set to {limit}" if limit > 0 else "👥 Removed user limit"
        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command(name="rename", description="🏷️ Rename your temporary channel")
    @channel_allowed(__file__)
    async def rename(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        sanitized = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        if not sanitized:
            await interaction.response.send_message(
                "❌ Invalid channel name. Use alphanumeric characters, spaces, hyphens, or underscores.",
                ephemeral=True,
            )
            return
        await channel.edit(name=sanitized)
        await interaction.response.send_message(f"🏷️ Channel renamed to {sanitized}", ephemeral=True)

    @app_commands.command(name="set-status", description="💬 Set status for your channel")
    @channel_allowed(__file__)
    async def set_status(
        self, interaction: discord.Interaction, status: app_commands.Range[str, 1, 500]
    ) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        await channel.edit(status=status)
        await interaction.response.send_message(f"💬 Status set to {status}", ephemeral=True)

    @app_commands.command(name="kick", description="👢 Kick a user from your channel")
    @channel_allowed(__file__)
    async def kick(
        self, interaction: discord.Interaction, member: discord.Member
    ) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        if member.voice and member.voice.channel == channel:
            await member.move_to(None)
            await interaction.response.send_message(
                f"👢 Kicked {member.display_name}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {member.display_name} isn't in your channel", ephemeral=True
            )

    @app_commands.command(name="mute", description="🔇 Mute a user in your channel")
    @channel_allowed(__file__)
    async def mute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        if member.voice and member.voice.channel == channel:
            await member.edit(mute=True)
            await interaction.response.send_message(f"🔇 Muted {member.display_name}", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"❌ {member.display_name} isn't in your channel", ephemeral=True
            )

    @app_commands.command(name="unmute", description="🔊 Unmute a user in your channel")
    @channel_allowed(__file__)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member) -> None:
        channel = await self._verify_owner(interaction)
        if not channel:
            return
        if member.voice and member.voice.channel == channel:
            await member.edit(mute=False)
            await interaction.response.send_message(
                f"🔊 Unmuted {member.display_name}", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ {member.display_name} isn't in your channel", ephemeral=True
            )


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(TempChannels(bot))
