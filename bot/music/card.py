from __future__ import annotations

import contextlib
import itertools
import time
from typing import TYPE_CHECKING

import discord

from bot.services.youtube import Track

if TYPE_CHECKING:
    from bot.cogs.music import MusicCog
    from bot.music.player import GuildPlayer

BAR_WIDTH = 18

LOOP_LABELS = {"off": "off", "track": "track", "queue": "queue"}


def format_seconds(seconds: float | int | None) -> str:
    if not seconds or seconds < 0:
        return "0:00"
    total = int(seconds)
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{sec:02}"
    return f"{minutes}:{sec:02}"


def _progress_bar(player: GuildPlayer) -> str:
    duration = player.current.duration if player.current else None
    pos = player.position
    if not duration:
        return "`◇ no duration`"
    ratio = max(0.0, min(pos / duration, 1.0))
    filled = round(BAR_WIDTH * ratio)
    bar = "━" * filled + "💠" + "━" * (BAR_WIDTH - filled)
    return f"`{bar}` `{format_seconds(pos)} / {format_seconds(duration)}`"


def _events_field(player: GuildPlayer) -> discord.Embed:
    embed = discord.Embed()
    if player.events:
        embed.add_field(
            name="Recent",
            value="\n".join(reversed(player.events)),
            inline=False,
        )
    return embed


def render_card(player: GuildPlayer) -> discord.Embed:
    if player.page == "queue" and (player.queue or player.current):
        return _render_queue(player)
    if player.current is None:
        return _render_idle(player)
    return _render_now(player)


def _render_now(player: GuildPlayer) -> discord.Embed:
    track = player.current
    assert track is not None
    badge = {"track": " 🔁", "queue": " 🔄"}.get(player.loop_mode, "")
    embed = discord.Embed(
        title=f"🎶 {track.title}{badge}",
        url=track.page_url,
        color=discord.Color.blurple(),
    )
    if track.author:
        embed.set_author(name=track.author)
    description = _progress_bar(player)
    if track.requester:
        description += f"\n-# Requested by **{track.requester}**"
    embed.description = description
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    queued = list(itertools.islice(player.queue, 50))
    total_left = sum(t.duration or 0 for t in queued)
    if player.queue:
        nxt = player.queue[0]
        embed.add_field(
            name="Up next",
            value=f"[{nxt.title[:60]}]({nxt.page_url})",
            inline=True,
        )
        embed.add_field(
            name="Queue",
            value=f"{len(player.queue)} tracks • {format_seconds(total_left)}",
            inline=True,
        )
    else:
        embed.add_field(name="Queue", value="Empty — ➕ to add", inline=True)
    if player.events:
        embed.add_field(
            name="Recent",
            value="\n".join(reversed(player.events)),
            inline=False,
        )
    embed.set_footer(text=f"Volume {round(player.volume * 100)}%")
    return embed


def _render_idle(player: GuildPlayer) -> discord.Embed:
    embed = discord.Embed(
        title="💤 Nothing playing",
        description="Queue is empty — press ➕ or use `/music play`.",
        color=discord.Color.greyple(),
    )
    if player.events:
        embed.add_field(
            name="Recent",
            value="\n".join(reversed(player.events)),
            inline=False,
        )
    return embed


def _render_queue(player: GuildPlayer) -> discord.Embed:
    queued = list(player.queue)
    total = sum(t.duration or 0 for t in queued)
    embed = discord.Embed(
        title=f"📜 Queue — {len(queued)} tracks • {format_seconds(total)} • Loop: {LOOP_LABELS[player.loop_mode]}",
        color=discord.Color.blurple(),
    )
    if player.current:
        embed.description = (
            f"**Now:** [{player.current.title[:70]}]({player.current.page_url})"
        )

    per_page = 10
    pages = max(1, -(-len(queued) // per_page))
    player.queue_page = max(0, min(player.queue_page, pages - 1))
    start = player.queue_page * per_page
    chunk = queued[start : start + per_page]
    lines = [
        f"**{start + i}.** [{t.title[:60]}]({t.page_url})"
        + (f" — {t.requester}" if t.requester else "")
        for i, t in enumerate(chunk, start=1)
    ]
    if lines:
        embed.add_field(name="Tracks", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Tracks", value="Queue is empty.", inline=False)
    embed.set_footer(text=f"Page {player.queue_page + 1}/{pages}")
    return embed


def render_tombstone(player: GuildPlayer) -> discord.Embed:
    embed = discord.Embed(
        title="🏁 Session ended",
        color=discord.Color.dark_grey(),
        description=(
            f"{player.tracks_played} tracks • {format_seconds(player.listen_seconds)} listened"
        ),
    )
    tops = []

    def _top(counter, verb):
        if not counter:
            return
        names = ", ".join(f"{name} ×{n}" for name, n in counter.most_common(3))
        tops.append(f"{verb}: {names}")

    _top(player.adds, "Added")
    _top(player.skips, "Skipped")
    if tops:
        embed.add_field(name="Stats", value="\n".join(tops), inline=False)
    return embed


class PlayerCardView(discord.ui.View):
    def __init__(self, cog: MusicCog, player: GuildPlayer) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.player = player
        self._last_press: dict[tuple[int, str], float] = {}

    def _cid(self, name: str) -> str:
        return f"duh:{self.player.guild.id}:{name}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        player = self.player
        if interaction.guild_id != player.guild.id:
            return False
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""
        action = custom_id.rsplit(":", 1)[-1]
        key = (interaction.user.id, action)
        now = time.monotonic()
        if now - self._last_press.get(key, 0.0) < 0.5:
            await interaction.response.defer()
            return False
        self._last_press[key] = now
        return True

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        await self.cog.act_prev(self.player, interaction.user.display_name)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary)
    async def play_pause(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        await self.cog.act_play_pause(self.player, interaction.user.display_name)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        await self.cog.act_skip(self.player, interaction.user.display_name)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        mode = self.player.cycle_loop()
        self.player.note_event(f"🔁 Loop → {LOOP_LABELS[mode]} ({interaction.user.display_name})")

    @discord.ui.button(emoji="🔀", style=discord.ButtonStyle.secondary)
    async def shuffle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        await self.cog.act_shuffle(self.player, interaction.user.display_name)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def page_toggle(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.player.page = "now" if self.player.page == "queue" else "queue"
        self.player.touch_card()

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.success, row=1)
    async def add_song(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(AddSongModal(self.cog, self.player))

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def volume(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(VolumeModal(self.cog, self.player))

    @discord.ui.button(emoji="🎤", style=discord.ButtonStyle.secondary, row=1)
    async def lyrics(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        await self.cog.act_lyrics(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=1)
    async def stop(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.defer()
        self.stop()
        await self.cog.act_stop(self.player, interaction.user.display_name)


class VolumeModal(discord.ui.Modal, title="Set Volume"):
    volume_input = discord.ui.TextInput(
        label="Volume percent (0-150)",
        placeholder="e.g. 75",
        max_length=4,
    )

    def __init__(self, cog: MusicCog, player: GuildPlayer) -> None:
        super().__init__()
        self.cog = cog
        self.player = player
        self.volume_input.default = str(round(player.volume * 100))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            percent = int(self.volume_input.value.strip().rstrip("%"))
        except ValueError:
            await interaction.followup.send("❌ Enter a number 0-150.", ephemeral=True)
            return
        percent = max(0, min(percent, 150))
        self.player.set_volume(percent / 100)
        self.player.note_event(
            f"🔊 Volume {round(self.player.volume * 100)}% ({interaction.user.display_name})"
        )
        await interaction.followup.send(
            f"🔊 Volume {round(self.player.volume * 100)}%", ephemeral=True
        )


class AddSongModal(discord.ui.Modal, title="Add a Song"):
    query_input = discord.ui.TextInput(
        label="Song name or YouTube URL",
        placeholder="e.g. night of nights",
        max_length=500,
    )

    def __init__(self, cog: MusicCog, player: GuildPlayer) -> None:
        super().__init__()
        self.cog = cog
        self.player = player

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await self.cog.act_add(interaction, self.player, self.query_input.value.strip())


class SearchPickerView(discord.ui.View):
    def __init__(
        self,
        cog: MusicCog,
        player: GuildPlayer,
        results: list[Track],
        requester: str,
        timeout: float,
    ) -> None:
        super().__init__(timeout=timeout)
        self.cog = cog
        self.player = player
        self.results = results
        self.requester = requester
        self.message: discord.abc.Message | None = None
        options = [
            discord.SelectOption(
                label=t.title[:100],
                description=(t.author or "")[:100] or None,
                value=str(index),
            )
            for index, t in enumerate(results)
        ]
        self.select = discord.ui.Select(
            placeholder="Pick a track…", options=options
        )
        self.select.callback = self._picked
        self.add_item(self.select)

    async def _picked(self, interaction: discord.Interaction) -> None:
        index = int(self.select.values[0])
        track = self.results[index]
        self.select.disabled = True
        self.select.placeholder = f"✓ {track.title[:80]}"
        await interaction.response.edit_message(view=self)
        await self.cog.act_enqueue(interaction, self.player, [track], requester=self.requester)
        self.stop()

    async def on_timeout(self) -> None:
        self.select.disabled = True
        if self.message:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=None)
