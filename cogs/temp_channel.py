import discord
from discord.ext import commands
from discord import app_commands


class TempChannel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_channels = {}

    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            category = discord.utils.get(guild.categories, name="TEMP CHANNELS")
            if category is None:
                category = await guild.create_category("TEMP CHANNELS")

            lobby_channel = discord.utils.get(
                category.voice_channels, name="Join to create"
            )
            if lobby_channel is None:
                await category.create_voice_channel("Join to create")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        category = discord.utils.get(guild.categories, name="TEMP CHANNELS")
        lobby_channel = discord.utils.get(
            category.voice_channels, name="Join to create"
        )

        if after.channel and after.channel.id == lobby_channel.id:
            if member.id in self.temp_channels:
                temp_vc = guild.get_channel(self.temp_channels[member.id])
                await member.move_to(temp_vc)
                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(connect=False),
                member: discord.PermissionOverwrite(manage_channels=True, connect=True),
            }
            temp_vc = await guild.create_voice_channel(
                name=f"{member.display_name}'s Channel",
                overwrites=overwrites,
                category=lobby_channel.category,
            )
            self.temp_channels[member.id] = temp_vc.id
            await member.move_to(temp_vc)

        for user_id, channel_id in list(self.temp_channels.items()):
            channel = guild.get_channel(channel_id)
            if channel and len(channel.members) == 0:
                await channel.delete()
                del self.temp_channels[user_id]
                print(f"Deleted empty temp channel {channel}")

    @app_commands.command(name="lock", description="Lock your temporary channel")
    async def lock(self, interaction: discord.Interaction):
        if interaction.user.id in self.temp_channels:
            channel = interaction.guild.get_channel(
                self.temp_channels[interaction.user.id]
            )
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            await interaction.response.send_message("Your channel is now locked.")
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel."
            )

    @app_commands.command(name="unlock", description="Unlock your temporary channel")
    async def unlock(self, interaction: discord.Interaction):
        if interaction.user.id in self.temp_channels:
            channel = interaction.guild.get_channel(
                self.temp_channels[interaction.user.id]
            )
            await channel.set_permissions(interaction.guild.default_role, connect=True)
            await interaction.response.send_message("Your channel is now unlocked.")
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel."
            )

    @app_commands.command(name="rename", description="Rename your temporary channel")
    async def rename(self, interaction: discord.Interaction, *, name: str):
        if interaction.user.id in self.temp_channels:
            channel = interaction.guild.get_channel(
                self.temp_channels[interaction.user.id]
            )
            await channel.edit(name=name)
            await interaction.response.send_message(
                f"Your channel has been renamed to {name}."
            )
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel."
            )

    @app_commands.command(
        name="limit", description="Set the user limit for your temporary channel"
    )
    async def limit(self, interaction: discord.Interaction, number: int):
        if interaction.user.id in self.temp_channels:
            channel = interaction.guild.get_channel(
                self.temp_channels[interaction.user.id]
            )
            await channel.edit(user_limit=number)
            await interaction.response.send_message(
                f"The user limit for your channel is now set to {number}."
            )
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel."
            )

    @app_commands.command(
        name="kick", description="Kick a member from your temporary channel"
    )
    async def kick(self, interaction: discord.Interaction, member: discord.Member):
        if interaction.user.id in self.temp_channels:
            channel = interaction.guild.get_channel(
                self.temp_channels[interaction.user.id]
            )
            if member in channel.members:
                await member.move_to(None)
                await interaction.response.send_message(
                    f"{member.display_name} has been kicked from your channel."
                )
            else:
                await interaction.response.send_message(
                    f"{member.display_name} is not in your channel."
                )
        else:
            await interaction.response.send_message(
                "You don't own a temporary channel."
            )


async def setup(bot):
    await bot.add_cog(TempChannel(bot))
