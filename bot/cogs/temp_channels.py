<<<<<<< HEAD
<<<<<<< HEAD
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.logger import BASE_LOG_FILE_NAME, setup_logger

# Constants
CATEGORY_NAME = "Temporary Channels"
TEMPLATE_CHANNEL_NAME = "Join to Create"

logger = setup_logger(
    name="temp_channels",
    log_to_file=True,
    log_file=BASE_LOG_FILE_NAME,
)


class TempChannels(commands.GroupCog, name="temp_channels"):
    """GroupCog for managing temporary voice channels."""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.temp_channels: dict[int, dict] = (
            {}
        )  # {channel_id: {"owner": user_id, "guild_id": guild_id}}

    async def __check_user_in_temp_channel(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceChannel]:
        """Check if the user is in their temporary channel."""
        if (
            not interaction.user.voice
            or interaction.user.voice.channel.id not in self.temp_channels
        ):
            await interaction.response.send_message(
                "You are not in your temporary channel.", ephemeral=True
            )
            return None
        return interaction.user.voice.channel

    async def __ensure_category_and_template(self, guild: discord.Guild):
        """Ensure the category and template channel exist."""
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if not category:
            category = await guild.create_category(CATEGORY_NAME)
            logger.info(
                f"Created category '{CATEGORY_NAME}' on server {guild.name} ({guild.id})."
            )

        template_channel = discord.utils.get(
            category.channels, name=TEMPLATE_CHANNEL_NAME
        )
        if not template_channel:
            await category.create_voice_channel(TEMPLATE_CHANNEL_NAME)
            logger.info(
                f"Created template channel '{TEMPLATE_CHANNEL_NAME}' on server {guild.name} ({guild.id})."
            )

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure the category and template channel exist when the bot is ready."""
        for guild in self.bot.guilds:
            await self.__ensure_category_and_template(guild)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle creating and cleaning up temporary voice channels."""
        category = discord.utils.get(member.guild.categories, name=CATEGORY_NAME)
        if not category:
            return

        # Create a new temporary channel if the user joins the template channel
        if after.channel and after.channel.name == TEMPLATE_CHANNEL_NAME:
            try:
                channel_name = f"{member.display_name}'s Channel"
                temp_channel = await category.create_voice_channel(
                    name=channel_name, user_limit=4
                )
                await member.move_to(temp_channel)
                self.temp_channels[temp_channel.id] = {
                    "owner": member.id,
                    "guild_id": member.guild.id,
                }
                logger.info(
                    f"Created temporary channel '{channel_name}' ({temp_channel.id}) on server {member.guild.name} ({member.guild.id})."
                )
            except Exception as e:
                logger.error(f"Failed to create temporary channel: {e}")

        # Delete the temporary channel if it's empty
        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                try:
                    logger.info(
                        f"Deleted temporary channel '{before.channel.name}' ({before.channel.id}) on server {member.guild.name} ({member.guild.id})."
                    )
                    await before.channel.delete()
                    del self.temp_channels[before.channel.id]
                except Exception as e:
                    logger.error(f"Failed to delete temporary channel: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.VoiceChannel):
        """Cleanup when a temp channel is deleted manually."""
        if channel.id in self.temp_channels:
            del self.temp_channels[channel.id]
            logger.warning(
                f"Manually deleted temporary channel '{channel.name}' ({channel.id}) on server {channel.guild.name} ({channel.guild.id})."
            )

    # =======================LOCK=======================
    @app_commands.command(name="lock", description="Lock your temporary channel.")
    async def lock(self, interaction: discord.Interaction):
        """Lock the user's temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        logger.debug(f"Locked channel '{channel.name}'.")
        await interaction.response.send_message(
            f"'{channel.name}' is now locked.", ephemeral=True
        )

    # ======================UNLOCK======================
    @app_commands.command(name="unlock", description="Unlock your temporary channel.")
    async def unlock(self, interaction: discord.Interaction):
        """Unlock the user's temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.set_permissions(interaction.guild.default_role, connect=True)
        logger.debug(f"Unlocked channel '{channel.name}'.")
        await interaction.response.send_message(
            f"'{channel.name}' is now unlocked.", ephemeral=True
        )

    # ======================LIMIT=======================
=======
import discord
from discord.ext import commands
from discord import app_commands


# FIXME:
class TempChannelsGroup(app_commands.Group):
    """Cog for managing temporary voice channels."""

    def __init__(self, bot: commands.Bot):
        super().__init__(name="temp-channels", description="Manage temporary channels.")
        self.temp_channels = (
            {}
        )  # {channel_id: {"owner": user_id, "guild_id": guild_id}}

    async def __get_category(self, guild: discord.Guild) -> discord.CategoryChannel:
        """Get or create the 'TEMP CHANNELS' category."""
        category = discord.utils.get(guild.categories, name="TEMP CHANNELS")
        if category is None:
            category = await guild.create_category("TEMP CHANNELS")
            print("CREATE CATEGORY")
        return category

    async def __create_temp_channel(
        self, member: discord.Member, category: discord.CategoryChannel
    ) -> discord.VoiceChannel:
        """Create a temporary voice channel for the member."""
        channel_name = f"{member.display_name}'s Channel"
        temp_channel = await category.create_voice_channel(
            name=channel_name, user_limit=0
        )
        await member.move_to(temp_channel)
        self.temp_channels[temp_channel.id] = {
            "owner": member.id,
            "guild_id": member.guild.id,
        }
        return temp_channel

    async def __delete_temp_channel(self, channel: discord.VoiceChannel):
        """Delete a temporary channel if it's empty."""
        if len(channel.members) == 0:
            await channel.delete()
            del self.temp_channels[channel.id]
            print(f"Deleted empty temp channel {channel.name}")

    async def __get_user_temp_channel(
        self, interaction: discord.Interaction
    ) -> discord.VoiceChannel | None:
        """Get the user's temporary channel."""
        for channel_id, info in self.temp_channels.items():
            if (
                info["owner"] == interaction.user.id
                and info["guild_id"] == interaction.guild.id
            ):
                return interaction.guild.get_channel(channel_id)
        return None

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure the 'TEMP CHANNELS' category and lobby channel exist."""
        print("ON_READY")
        for guild in self.bot.guilds:
            category = await self.__get_category(guild)
            if not discord.utils.get(category.voice_channels, name="Join to create"):
                print("CREATE VC")
                await category.create_voice_channel("Join to create")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Create and delete temp channels on user voice state updates."""
        print("UPDATE")
        if before.channel == after.channel:  # No change in channel
            return

        # 'Join to Create' logic
        if after.channel and after.channel.name.lower() == "join to create":
            category = await self.__get_category(member.guild)
            await self.__create_temp_channel(member, category)

        if before.channel and before.channel.id in self.temp_channels:
            await self.__delete_temp_channel(before.channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Cleanup when a temp channel is deleted manually."""
        if channel.id in self.temp_channels:
            del self.temp_channels[channel.id]

    async def __update_channel_permissions(
        self,
        temp_channel: discord.VoiceChannel,
        interaction: discord.Interaction,
        allow: bool,
    ):
        """Helper function to lock/unlock the channel."""
        await temp_channel.set_permissions(
            interaction.guild.default_role, connect=allow
        )
        action = "locked" if not allow else "unlocked"
        return f"Your channel has been {action}."

    @app_commands.command(name="lock", description="Lock your temporary channel.")
    async def lock(self, interaction: discord.Interaction):
        """Lock the user's temporary channel."""
        temp_channel = await self.__get_user_temp_channel(interaction)
        if temp_channel:
            message = await self.__update_channel_permissions(
                temp_channel, interaction, False
            )
            await interaction.response.send_message(message)
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel.", ephemeral=True
            )

    @app_commands.command(name="unlock", description="Unlock your temporary channel.")
    async def unlock(self, interaction: discord.Interaction):
        """Unlock the user's temporary channel."""
        temp_channel = await self.__get_user_temp_channel(interaction)
        if temp_channel:
            message = await self.__update_channel_permissions(
                temp_channel, interaction, True
            )
            await interaction.response.send_message(message)
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel.", ephemeral=True
            )

    @app_commands.command(name="rename", description="Rename your temporary channel.")
    async def rename(self, interaction: discord.Interaction, name: str):
        """Rename the user's temporary channel."""
        temp_channel = await self.__get_user_temp_channel(interaction)
        if temp_channel:
            await temp_channel.edit(name=name)
            await interaction.response.send_message(
                f"Your channel has been renamed to: {name}."
            )
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel.", ephemeral=True
            )

>>>>>>> f5ed92a (logger, better code, fixes)
    @app_commands.command(
        name="limit", description="Set a user limit for your temporary channel."
    )
    async def limit(self, interaction: discord.Interaction, limit: int):
<<<<<<< HEAD
        """Set a user limit for the temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.edit(user_limit=limit)
        logger.debug(f"Set user limit for '{channel.name}' to {limit}.")
        await interaction.response.send_message(
            f"User limit for '{channel.name}' is now set to {limit}.", ephemeral=True
        )

    # =======================KICK=======================
=======
        """Set the user limit for the user's temporary channel."""
        temp_channel = await self.__get_user_temp_channel(interaction)
        if temp_channel:
            await temp_channel.edit(user_limit=limit)
            await interaction.response.send_message(f"User limit set to: {limit}.")
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel.", ephemeral=True
            )

>>>>>>> f5ed92a (logger, better code, fixes)
    @app_commands.command(
        name="kick", description="Kick a user from your temporary channel."
    )
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
<<<<<<< HEAD
        """Kick a user from the temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        if member.voice and member.voice.channel == channel:
            await member.move_to(None)  # Move the member out of the channel
            logger.debug(f"Kicked {member.display_name} from '{channel.name}'.")
            await interaction.response.send_message(
                f"Kicked {member.display_name} from '{channel.name}'.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{member.display_name} is not in your channel.", ephemeral=True
            )

    # ======================RENAME======================
    @app_commands.command(name="rename", description="Rename your temporary channel.")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        """Rename the user's temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.edit(name=new_name)
        logger.debug(f"Renamed channel to '{new_name}'.")
        await interaction.response.send_message(
            f"Your channel has been renamed to '{new_name}'.", ephemeral=True
        )


async def setup(bot: commands.Bot):
=======
        """Kick a member from the user's temporary channel."""
        temp_channel = await self.__get_user_temp_channel(interaction)
        if temp_channel and member.voice and member.voice.channel == temp_channel:
            await member.move_to(None)  # Disconnect the user
            await interaction.response.send_message(
                f"{member.display_name} has been kicked from your channel."
            )
        else:
            await interaction.response.send_message(
                "The user is not in your channel or you don't own a temporary channel.",
                ephemeral=True,
            )


class TempChannels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.tree.add_command(TempChannelsGroup(bot))


async def setup(bot: commands.Bot):
    """Setup function to load the cog."""
>>>>>>> f5ed92a (logger, better code, fixes)
    await bot.add_cog(TempChannels(bot))
=======
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.logger import setup_logger

# Constants
CATEGORY_NAME = "Temporary Channels"
TEMPLATE_CHANNEL_NAME = "Join to Create"

logger = setup_logger(name="temp_channels")


class TempChannels(commands.GroupCog, name="temp_channels"):
    """GroupCog for managing temporary voice channels."""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.temp_channels: dict[int, dict] = (
            {}
        )  # {channel_id: {"owner": user_id, "guild_id": guild_id}}

    async def __check_user_in_temp_channel(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceChannel]:
        """Check if the user is in their temporary channel."""
        if (
            not interaction.user.voice
            or interaction.user.voice.channel.id not in self.temp_channels
        ):
            await interaction.response.send_message(
                "You are not in your temporary channel.", ephemeral=True
            )
            return None
        return interaction.user.voice.channel

    async def __ensure_category_and_template(self, guild: discord.Guild):
        """Ensure the category and template channel exist."""
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        if not category:
            category = await guild.create_category(CATEGORY_NAME)
            logger.info(
                f"Created category '{CATEGORY_NAME}' on server {guild.name} ({guild.id})."
            )

        template_channel = discord.utils.get(
            category.channels, name=TEMPLATE_CHANNEL_NAME
        )
        if not template_channel:
            await category.create_voice_channel(TEMPLATE_CHANNEL_NAME)
            logger.info(
                f"Created template channel '{TEMPLATE_CHANNEL_NAME}' on server {guild.name} ({guild.id})."
            )

    @commands.Cog.listener()
    async def on_ready(self):
        """Ensure the category and template channel exist when the bot is ready."""
        for guild in self.bot.guilds:
            await self.__ensure_category_and_template(guild)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Handle creating and cleaning up temporary voice channels."""
        category = discord.utils.get(member.guild.categories, name=CATEGORY_NAME)
        if not category:
            return

        # Create a new temporary channel if the user joins the template channel
        if after.channel and after.channel.name == TEMPLATE_CHANNEL_NAME:
            try:
                channel_name = f"{member.display_name}'s Channel"
                temp_channel = await category.create_voice_channel(
                    name=channel_name, user_limit=4
                )
                await member.move_to(temp_channel)
                self.temp_channels[temp_channel.id] = {
                    "owner": member.id,
                    "guild_id": member.guild.id,
                }
                logger.info(
                    f"Created temporary channel '{channel_name}' ({temp_channel.id}) on server {member.guild.name} ({member.guild.id})."
                )
            except Exception as e:
                logger.error(f"Failed to create temporary channel: {e}", exc_info=True)

        # Delete the temporary channel if it's empty
        if before.channel and before.channel.id in self.temp_channels:
            if len(before.channel.members) == 0:
                try:
                    logger.info(
                        f"Deleted temporary channel '{before.channel.name}' ({before.channel.id}) on server {member.guild.name} ({member.guild.id})."
                    )
                    await before.channel.delete()
                    del self.temp_channels[before.channel.id]
                except Exception as e:
                    logger.error(
                        f"Failed to delete temporary channel: {e}", exc_info=True
                    )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.VoiceChannel):
        """Cleanup when a temp channel is deleted manually."""
        if channel.id in self.temp_channels:
            del self.temp_channels[channel.id]
            logger.warning(
                f"Manually deleted temporary channel '{channel.name}' ({channel.id}) on server {channel.guild.name} ({channel.guild.id})."
            )

    # =======================LOCK=======================
    @app_commands.command(name="lock", description="Lock your temporary channel.")
    async def lock(self, interaction: discord.Interaction):
        """Lock the user's temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.set_permissions(interaction.guild.default_role, connect=False)
        logger.debug(f"Locked channel '{channel.name}'.")
        await interaction.response.send_message(
            f"'{channel.name}' is now locked.", ephemeral=True
        )

    # ======================UNLOCK======================
    @app_commands.command(name="unlock", description="Unlock your temporary channel.")
    async def unlock(self, interaction: discord.Interaction):
        """Unlock the user's temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.set_permissions(interaction.guild.default_role, connect=True)
        logger.debug(f"Unlocked channel '{channel.name}'.")
        await interaction.response.send_message(
            f"'{channel.name}' is now unlocked.", ephemeral=True
        )

    # ======================LIMIT=======================
    @app_commands.command(
        name="limit", description="Set a user limit for your temporary channel."
    )
    async def limit(self, interaction: discord.Interaction, limit: int):
        """Set a user limit for the temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.edit(user_limit=limit)
        logger.debug(f"Set user limit for '{channel.name}' to {limit}.")
        await interaction.response.send_message(
            f"User limit for '{channel.name}' is now set to {limit}.", ephemeral=True
        )

    # =======================KICK=======================
    @app_commands.command(
        name="kick", description="Kick a user from your temporary channel."
    )
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        """Kick a user from the temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        if member.voice and member.voice.channel == channel:
            await member.move_to(None)  # Move the member out of the channel
            logger.debug(f"Kicked {member.display_name} from '{channel.name}'.")
            await interaction.response.send_message(
                f"Kicked {member.display_name} from '{channel.name}'.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"{member.display_name} is not in your channel.", ephemeral=True
            )

    # ======================RENAME======================
    @app_commands.command(name="rename", description="Rename your temporary channel.")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        """Rename the user's temporary channel."""
        channel = await self.__check_user_in_temp_channel(interaction)
        if not channel:
            return

        await channel.edit(name=new_name)
        logger.debug(f"Renamed channel to '{new_name}'.")
        await interaction.response.send_message(
            f"Your channel has been renamed to '{new_name}'.", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TempChannels(bot))
>>>>>>> 489c3f3 (changed to ffmpegOpus, added shuffle, skip, help commands, better playlist handling)
