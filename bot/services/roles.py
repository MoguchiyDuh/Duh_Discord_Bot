from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)

ROLES_CHANNEL = "roles"


@dataclass(frozen=True, slots=True)
class RoleSpec:
    name: str
    description: str | None = None
    color: int = 0


@dataclass(frozen=True, slots=True)
class RoleGroup:
    key: str
    label: str
    emoji: str
    single: bool
    roles: tuple[RoleSpec, ...]


PROGRAMME = RoleGroup(
    "programme",
    "Programme",
    "🎓",
    True,
    (
        RoleSpec("CS", "Computer Science"),
        RoleSpec("IT", "Information Technology"),
        RoleSpec("SDE", "Software and Data Engineering"),
        RoleSpec("AAI", "Applied Artificial Intelligence"),
    ),
)

YEAR = RoleGroup(
    "year",
    "Year",
    "📅",
    True,
    tuple(RoleSpec(f"Year {n}") for n in range(1, 5)),
)

OS = RoleGroup(
    "os",
    "OS",
    "💻",
    False,
    (RoleSpec("GNU/Linux"), RoleSpec("Windows"), RoleSpec("macOS")),
)

DISTRO = RoleGroup(
    "distro",
    "Distro",
    "🐧",
    True,
    tuple(
        RoleSpec(name)
        for name in (
            "Arch",
            "Debian",
            "Ubuntu",
            "Fedora",
            "Linux Mint",
            "NixOS",
            "Gentoo",
            "openSUSE",
            "Pop!_OS",
            "Manjaro",
            "EndeavourOS",
            "CachyOS",
            "Kali",
            "Other distro",
        )
    ),
)

LANGUAGES = RoleGroup(
    "languages",
    "Languages",
    "🧑‍💻",
    False,
    (
        RoleSpec("Python", color=0x3572A5),
        RoleSpec("Rust", color=0xDEA584),
        RoleSpec("C/C++", color=0xF34B7D),
        RoleSpec("C#", color=0x178600),
        RoleSpec("Java", color=0xB07219),
        RoleSpec("Kotlin", color=0xA97BFF),
        RoleSpec("Go", color=0x00ADD8),
        RoleSpec("JS/TS", color=0xF1E05A),
        RoleSpec("Swift", color=0xF05138),
        RoleSpec("Lua", color=0x000080),
        RoleSpec("Zig", color=0xEC915C),
        RoleSpec("Assembly", color=0x6E4C13),
        RoleSpec("Vibe-code", color=0xFF69B4),
    ),
)

AREAS = RoleGroup(
    "areas",
    "Areas",
    "🧭",
    False,
    (
        RoleSpec("Frontend", "Web interfaces"),
        RoleSpec("Backend", "Servers, APIs, databases"),
        RoleSpec("Full-stack", "Frontend and backend"),
        RoleSpec("Mobile", "Android, iOS"),
        RoleSpec("Desktop", "Native apps: Qt, GTK, WPF, Electron"),
        RoleSpec("Gamedev", "Games and graphics"),
        RoleSpec("Data Science", "Analysis, pipelines, BI"),
        RoleSpec("ML/AI", "Models, training, inference"),
        RoleSpec("DevOps/Cloud", "CI/CD, containers, cloud, SRE"),
        RoleSpec("Linux/SysAdmin", "Servers and system administration"),
        RoleSpec("Networking", "Network engineering"),
        RoleSpec("Cybersecurity", "Offensive and defensive security"),
        RoleSpec("Embedded/IoT", "Microcontrollers, firmware, devices"),
        RoleSpec("QA/Testing", "Testing and quality assurance"),
        RoleSpec("UI/UX", "Interface and experience design"),
        RoleSpec("Blockchain", "Smart contracts, web3"),
    ),
)

INTERESTS = RoleGroup(
    "interests",
    "Interests",
    "✨",
    False,
    tuple(
        RoleSpec(name)
        for name in (
            "Gaming",
            "Music",
            "Anime",
            "Movies/Series",
            "Sports",
            "Memes",
            "PC Hardware",
        )
    ),
)

LINUX_ROLE = "GNU/Linux"

PANEL_GROUPS: tuple[RoleGroup, ...] = (PROGRAMME, YEAR, OS, LANGUAGES, AREAS, INTERESTS)
ALL_GROUPS: tuple[RoleGroup, ...] = (PROGRAMME, YEAR, OS, DISTRO, LANGUAGES, AREAS, INTERESTS)
GROUPS_BY_KEY: dict[str, RoleGroup] = {group.key: group for group in ALL_GROUPS}


class RoleService:
    def __init__(self, bot: DuhBot) -> None:
        self.bot = bot
        self._store_path = bot.settings.data_dir / "roles.json"
        self._data: dict[str, dict[str, Any]] = {}
        try:
            self._data = json.loads(self._store_path.read_text("utf-8"))
        except (OSError, ValueError):
            pass

    def _save(self) -> None:
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=1), "utf-8"
            )
        except OSError:
            logger.exception("Failed to persist role store")

    def _guild_store(self, guild_id: int) -> dict[str, Any]:
        return self._data.setdefault(str(guild_id), {})

    def _role_ids(self, guild_id: int) -> dict[str, int]:
        return self._guild_store(guild_id).setdefault("roles", {})

    def is_configured(self, guild_id: int) -> bool:
        return bool(self._data.get(str(guild_id), {}).get("roles"))

    def role(self, guild: discord.Guild, name: str) -> discord.Role | None:
        role_id = self._role_ids(guild.id).get(name)
        if role_id is None:
            return None
        return guild.get_role(role_id)

    def group_roles(self, guild: discord.Guild, group: RoleGroup) -> dict[str, discord.Role]:
        resolved: dict[str, discord.Role] = {}
        for spec in group.roles:
            if role := self.role(guild, spec.name):
                resolved[spec.name] = role
        return resolved

    async def ensure_roles(self, guild: discord.Guild) -> int:
        ids = self._role_ids(guild.id)
        created = 0
        for group in ALL_GROUPS:
            for spec in group.roles:
                existing = ids.get(spec.name)
                if existing is not None and guild.get_role(existing) is not None:
                    continue
                role = await guild.create_role(
                    name=spec.name,
                    permissions=discord.Permissions.none(),
                    colour=discord.Colour(spec.color),
                    hoist=False,
                    mentionable=True,
                    reason="Self-assignable role setup",
                )
                ids[spec.name] = role.id
                created += 1
                self._save()
        self._save()
        return created

    async def ensure_channel(self, guild: discord.Guild) -> discord.TextChannel:
        store = self._guild_store(guild.id)
        channel_id = store.get("channel")
        if isinstance(channel_id, int):
            channel = guild.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                return channel

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                add_reactions=False,
                create_public_threads=False,
                create_private_threads=False,
                send_messages_in_threads=False,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, embed_links=True
            ),
        }
        position = guild.rules_channel.position + 1 if guild.rules_channel else 0
        channel = await guild.create_text_channel(
            ROLES_CHANNEL,
            overwrites=overwrites,
            position=position,
            topic="Pick your roles",
            reason="Self-assignable role setup",
        )
        store["channel"] = channel.id
        store.pop("message", None)
        self._save()
        logger.info("Created #%s in %s", ROLES_CHANNEL, guild.name)
        return channel

    async def ensure_panel(
        self,
        channel: discord.TextChannel,
        embed: discord.Embed,
        view: discord.ui.View,
    ) -> discord.Message:
        store = self._guild_store(channel.guild.id)
        message_id = store.get("message")
        if isinstance(message_id, int):
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed, view=view)
                return message
            except discord.NotFound:
                pass
        message = await channel.send(embed=embed, view=view)
        store["message"] = message.id
        self._save()
        return message
