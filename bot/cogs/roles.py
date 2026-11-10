from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import EMBED_COLOR, BaseCog
from bot.services.roles import (
    DISTRO,
    LINUX_ROLE,
    OS,
    PANEL_GROUPS,
    RoleGroup,
    RoleService,
)

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

REASON = "Self-assigned via role panel"


def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎭 Pick your roles",
        description="Press a button to choose. Only you see the menu, and you can change it anytime.",
        color=EMBED_COLOR,
    )
    for group in PANEL_GROUPS:
        names = ", ".join(spec.name for spec in group.roles)
        hint = "pick one" if group.single else "pick any"
        embed.add_field(name=f"{group.emoji} {group.label} · {hint}", value=names, inline=False)
    embed.set_footer(text="Pick GNU/Linux under OS to choose your distro")
    return embed


class GroupSelect(discord.ui.Select["PickerView"]):
    def __init__(
        self,
        group: RoleGroup,
        roles: dict[str, discord.Role],
        held: set[int],
        row: int,
    ) -> None:
        self.group = group
        self.roles = roles
        options = [
            discord.SelectOption(
                label=spec.name,
                value=spec.name,
                description=spec.description,
                default=roles[spec.name].id in held,
            )
            for spec in group.roles
            if spec.name in roles
        ]
        super().__init__(
            placeholder=f"{group.emoji} {group.label}",
            min_values=0,
            max_values=1 if group.single else len(options),
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.apply(interaction, self.group, set(self.values))


class PickerView(discord.ui.View):
    def __init__(
        self,
        service: RoleService,
        member: discord.Member,
        group: RoleGroup,
        held: set[int],
    ) -> None:
        super().__init__(timeout=300)
        self.service = service
        self.member = member
        self.group = group
        self.held = held
        guild = member.guild
        self.add_item(GroupSelect(group, service.group_roles(guild, group), held, row=0))
        if group is OS and self._has_linux():
            self.add_item(GroupSelect(DISTRO, service.group_roles(guild, DISTRO), held, row=1))

    def _has_linux(self) -> bool:
        linux = self.service.role(self.member.guild, LINUX_ROLE)
        return linux is not None and linux.id in self.held

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.member.id

    def content(self) -> str:
        hint = "pick one" if self.group.single else "pick any"
        lines = [f"{self.group.emoji} **{self.group.label}** · {hint}"]
        if self.group is OS:
            lines.append(
                "🐧 Pick your distro below"
                if self._has_linux()
                else "🐧 Pick GNU/Linux to choose your distro"
            )
        return "\n".join(lines)

    async def apply(
        self, interaction: discord.Interaction, group: RoleGroup, selected: set[str]
    ) -> None:
        guild = self.member.guild
        group_roles = self.service.group_roles(guild, group)
        wanted = {role.id for name, role in group_roles.items() if name in selected}
        managed = {role.id for role in group_roles.values()}

        if group is OS and LINUX_ROLE not in selected:
            managed |= {role.id for role in self.service.group_roles(guild, DISTRO).values()}

        to_add = [guild.get_role(rid) for rid in wanted - self.held]
        to_remove = [guild.get_role(rid) for rid in (managed - wanted) & self.held]

        await interaction.response.defer()
        try:
            if to_remove:
                await self.member.remove_roles(*filter(None, to_remove), reason=REASON)
            if to_add:
                await self.member.add_roles(*filter(None, to_add), reason=REASON)
        except discord.HTTPException:
            logger.exception("Failed to update roles for %s", self.member)
            await interaction.edit_original_response(
                content="❌ Couldn't update your roles, try again later", view=None
            )
            return

        held = (self.held - managed) | wanted
        view = PickerView(self.service, self.member, self.group, held)
        await interaction.edit_original_response(content=view.content(), view=view)
        self.stop()


class PanelButton(discord.ui.Button["RolePanelView"]):
    def __init__(self, group: RoleGroup, index: int) -> None:
        super().__init__(
            label=group.label,
            emoji=group.emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"duh:roles:{group.key}",
            row=index // 3,
        )
        self.group = group

    async def callback(self, interaction: discord.Interaction) -> None:
        assert self.view is not None
        await self.view.open(interaction, self.group)


class RolePanelView(discord.ui.View):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        for index, group in enumerate(PANEL_GROUPS):
            self.add_item(PanelButton(group, index))

    async def open(self, interaction: discord.Interaction, group: RoleGroup) -> None:
        service = self.bot.roles
        member = interaction.user
        if (
            service is None
            or not isinstance(member, discord.Member)
            or not service.is_configured(member.guild.id)
        ):
            await interaction.response.send_message(
                "❌ Roles aren't set up on this server", ephemeral=True
            )
            return
        held = {role.id for role in member.roles}
        view = PickerView(service, member, group, held)
        await interaction.response.send_message(view.content(), view=view, ephemeral=True)


class Roles(BaseCog, commands.GroupCog, name="roles"):
    """🎭 Self-assignable roles"""

    async def cog_load(self) -> None:
        self.bot.add_view(RolePanelView(self.bot))

    @app_commands.command(
        name="setup", description="🎭 Create the self-assignable roles and the #roles panel"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_roles(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        service = self.bot.roles
        if guild is None or service is None:
            await interaction.response.send_message("❌ This command is guild-only", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        created = await service.ensure_roles(guild)
        channel = await service.ensure_channel(guild)
        await service.ensure_panel(channel, build_panel_embed(), RolePanelView(self.bot))
        logger.info("Role panel set up in %s by %s (%d new roles)", guild.name, interaction.user, created)
        await interaction.followup.send(
            f"✅ {created} new role(s), panel in {channel.mention}", ephemeral=True
        )


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(Roles(bot))
