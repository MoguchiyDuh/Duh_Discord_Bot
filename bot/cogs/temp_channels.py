from typing import TYPE_CHECKING, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands

from . import BaseCog, channel_allowed

if TYPE_CHECKING:
    from . import MyBot


# ========= TEMP CHANNEL COG ==========
class TempChannels(BaseCog, commands.GroupCog, name="temp_channels"):
    """GroupCog for managing temporary voice channels."""

    def __init__(self, bot: "MyBot"):
        super().__init__(bot)
        self.temp_channels: Dict[int, Dict[str, int]] = (
            {}
        )  # {channel_id: {"owner": user_id, "guild_id": guild_id}}
        self.logger = bot.logger.getChild("temp_channels")

    # ========== HELPERS ==========
    async def _verify_channel_owner(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceChannel]:
        """Verify user owns the temp channel they're in"""
        voice = interaction.user.voice
        if not voice or not voice.channel:
            await interaction.response.send_message(
                "❌ You must be in a voice channel", ephemeral=True
            )
            return None

        channel_data = self.temp_channels.get(voice.channel.id)

        if not channel_data:
            await interaction.response.send_message(
                "❌ You're not in a temporary channel", ephemeral=True
            )
            return None

        if channel_data["owner"] != interaction.user.id:
            await interaction.response.send_message(
                "❌ You don't own this channel", ephemeral=True
            )
            return None

        return voice.channel

    async def _ensure_temp_infrastructure(self, guild: discord.Guild) -> bool:
        """Ensure required channels/categories exist"""
        try:
            await self.channel_service.ensure_channels(guild)
            return True
        except Exception as e:
            self.logger.error(
                f"Failed to setup temp infrastructure in {guild.name}: {e}"
            )
            return False

    # ========== UNLOADER ==========
    async def cog_unload(self):
        """Delete tracked temp channels on unload."""
        self.logger.debug("Temp Channels unloader triggered")
        for channel_id, meta in list(self.temp_channels.items()):
            try:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    guild = self.bot.get_guild(meta["guild_id"])
                    channel = await guild.fetch_channel(channel_id) if guild else None
                if channel:
                    await channel.delete(reason="Cog unload cleanup")
            except Exception as e:
                self.logger.error(f"Failed to delete channel {channel_id}: {e}")
            finally:
                self.temp_channels.pop(channel_id, None)

    # ========== LISTENERS ==========
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle channel creation/deletion"""
        # Create new temp channel
        if (
            after.channel
            and after.channel.name
            in self.bot.channel_service.get_channel_name("voice_hub")
        ):
            if not await self._ensure_temp_infrastructure(member.guild):
                return

            try:
                category = discord.utils.get(
                    member.guild.categories,
                    name=self.channel_service.COMMAND_CATEGORIES[1],
                )
                if not category:
                    return

                temp_channel = await category.create_voice_channel(
                    name=f"{member.display_name}'s Room", user_limit=4
                )
                await member.move_to(temp_channel)
                self.temp_channels[temp_channel.id] = {
                    "owner": member.id,
                    "guild_id": member.guild.id,
                }
                self.logger.info(f"Created temp channel for @{member.name}")
            except Exception as e:
                self.logger.error(f"Failed to create temp channel: {e}")

        # Cleanup empty channels
        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                    self.logger.info(
                        f"Deleted empty temp channel {before.channel.name}"
                    )
                except Exception as e:
                    self.logger.error(f"Failed to delete temp channel: {e}")
                finally:
                    self.temp_channels.pop(before.channel.id, None)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Cleanup tracking if channel is deleted"""
        if channel.id in self.temp_channels:
            self.logger.warning(f"Voice chat #{channel.name} deleted manually")
            self.temp_channels.pop(channel.id)

    # ========== LOCK ==========
    @app_commands.command(name="lock", description="🔒 Lock your temporary channel")
    @channel_allowed(__file__)
    async def lock(self, interaction: discord.Interaction):
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /lock on #{channel.name}"
        )

        await channel.set_permissions(
            interaction.guild.default_role,
            connect=False,
            reason=f"Locked by {interaction.user.name}",
        )
        self.logger.info(f"Locked channel #{channel.name}")
        await interaction.response.send_message(
            f"🔒 {channel.mention} is now locked", ephemeral=True
        )

    # ========== UNLOCK ==========
    @app_commands.command(name="unlock", description="🔓 Unlock your temporary channel")
    @channel_allowed(__file__)
    async def unlock(self, interaction: discord.Interaction):
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /unlock on #{channel.name}"
        )

        await channel.set_permissions(
            interaction.guild.default_role,
            connect=True,
            reason=f"Unlocked by {interaction.user.name}",
        )
        self.logger.info(f"Unlocked channel #{channel.name}")
        await interaction.response.send_message(
            f"🔓 {channel.mention} is now unlocked", ephemeral=True
        )

    # ========== LIMIT ==========
    @app_commands.command(name="limit", description="👥 Set user limit (0-99)")
    @app_commands.describe(limit="Max number of users (0 for no limit)")
    @channel_allowed(__file__)
    async def limit(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 0, 99]
    ):
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /limit with limit: {limit}"
        )

        await channel.edit(user_limit=limit)
        msg = f"👥 User limit set to {limit}" if limit > 0 else "👥 Removed user limit"
        self.logger.info(f"Set user limit for #{channel.name} to {limit}")
        await interaction.response.send_message(msg, ephemeral=True)

    # ========== RENAME ==========
    @app_commands.command(name="rename", description="🏷️ Rename your temporary channel")
    @channel_allowed(__file__)
    async def rename(
        self, interaction: discord.Interaction, name: app_commands.Range[str, 1, 100]
    ):
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /rename with name: {name}"
        )

        # Sanitize channel name - remove potentially dangerous characters
        sanitized_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        if not sanitized_name:
            await interaction.response.send_message(
                "❌ Invalid channel name. Use alphanumeric characters, spaces, hyphens, or underscores.",
                ephemeral=True,
            )
            return

        old_name = channel.name
        await channel.edit(name=sanitized_name)
        self.logger.info(f"Channel #{old_name} renamed to #{channel.name}")
        await interaction.response.send_message(
            f"🏷️ Channel renamed to {name}", ephemeral=True
        )

    # ========== SET STATUS ==========
    @app_commands.command(name="set-status", description="Set status for your channel")
    @channel_allowed(__file__)
    async def set_status(
        self, interaction: discord.Interaction, status: app_commands.Range[str, 1, 100]
    ):
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /set_status with status: {status}"
        )

        await channel.edit(status=status)
        self.logger.info(f"Status set to {status} in #{channel.name}")
        await interaction.response.send_message(
            f"Status set to {status}", ephemeral=True
        )

    # ========== KICK ==========
    @app_commands.command(name="kick", description="👢 Kick a user from your channel")
    @channel_allowed(__file__)
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        """Kick a user from your channel"""
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /kick on @{member.name} from #{channel.name}"
        )

        if member.voice and member.voice.channel == channel:
            await member.move_to(None)
            self.logger.info(
                f"User @{member.name} has been kicked from #{channel.name}"
            )
            await interaction.response.send_message(
                f"👢 Kicked {member.display_name}", ephemeral=True
            )
        else:
            self.logger.warning(
                f"User @{member.name} isn't in #{channel.name} to be kicked"
            )
            await interaction.response.send_message(
                f"❌ {member.display_name} isn't in your channel", ephemeral=True
            )

    # ========== MUTE ==========
    @app_commands.command(name="mute", description="🔇 Mute a user in your channel")
    @channel_allowed(__file__)
    async def mute(self, interaction: discord.Interaction, member: discord.Member):
        """Mute a user in your channel"""
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /mute on @{member.name} in #{channel.name}"
        )

        if member.voice and member.voice.channel == channel:
            await member.edit(mute=True)
            self.logger.info(f"User @{member.name} has been muted in #{channel.name}")
            await interaction.response.send_message(
                f"🔇 Muted {member.display_name}", ephemeral=True
            )
        else:
            self.logger.warning(
                f"User @{member.name} isn't in #{channel.name} to be muted"
            )
            await interaction.response.send_message(
                f"❌ {member.display_name} isn't in your channel", ephemeral=True
            )

    @app_commands.command(name="unmute", description="🔊 Unmute a user in your channel")
    @channel_allowed(__file__)
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        """Unmute a user in your channel"""
        channel = await self._verify_channel_owner(interaction)
        if not channel:
            return
        self.logger.debug(
            f"User @{interaction.user.name} invoked /unmute on @{member.name} in #{channel.name}"
        )

        if member.voice and member.voice.channel == channel:
            await member.edit(mute=False)
            self.logger.info(f"User @{member.name} has been unmuted in #{channel.name}")
            await interaction.response.send_message(
                f"🔊 Unmuted {member.display_name}", ephemeral=True
            )
        else:
            self.logger.warning(
                f"User @{member.name} isn't in #{channel.name} to be unmuted"
            )
            await interaction.response.send_message(
                f"❌ {member.display_name} isn't in your channel", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TempChannels(bot))
