from __future__ import annotations

import contextlib
import io
import itertools
import logging
import random
import re
from collections import deque
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.cogs import EMBED_COLOR, BaseCog, channel_allowed
from bot.music.player import LOOP_MODES, GuildPlayer
from bot.music.views import NowPlayingView, PlaylistSelectionView, TrackSelectionView, parse_selection
from bot.services.lyrics import LyricsError
from bot.services.youtube import Track, YouTubeError

if TYPE_CHECKING:
    from bot.core.bot import DuhBot

logger = logging.getLogger(__name__)


def _member_voice(interaction: discord.Interaction) -> discord.VoiceState | None:
    if isinstance(interaction.user, discord.Member):
        return interaction.user.voice
    return None


def _text_channel(interaction: discord.Interaction) -> discord.abc.Messageable | None:
    if isinstance(interaction.channel, discord.abc.Messageable):
        return interaction.channel
    return None


class MusicCog(BaseCog, commands.GroupCog, name="music"):
    def __init__(self, bot: DuhBot) -> None:
        super().__init__(bot)
        self.players: dict[int, GuildPlayer] = {}

    @property
    def max_queue(self) -> int:
        return self.bot.settings.max_queue

    @property
    def idle_timeout(self) -> float:
        return self.bot.settings.idle_timeout

    @property
    def resolve_timeout(self) -> float:
        return self.bot.settings.resolve_timeout

    @property
    def search_timeout(self) -> float:
        return self.bot.settings.search_timeout

    @property
    def default_volume(self) -> float:
        return self.bot.settings.default_volume

    async def cog_unload(self) -> None:
        for guild_id in list(self.players):
            player = self.players.pop(guild_id, None)
            if player:
                await player.destroy()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        await self.destroy_player(guild)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id == self.bot.user.id:
            if after.channel is None:
                await self.destroy_player(member.guild)
            return

        player = self.players.get(member.guild.id)
        if not player or not player.voice or not player.voice.channel:
            return
        if len(player.voice.channel.members) == 1:
            logger.info("Alone in %s, disconnecting", member.guild.name)
            await self.destroy_player(member.guild)

    async def destroy_player(self, guild: discord.Guild) -> None:
        player = self.players.pop(guild.id, None)
        if player:
            await player.destroy()

    async def _get_player(self, interaction: discord.Interaction) -> GuildPlayer | None:
        voice_state = _member_voice(interaction)
        if not voice_state or not voice_state.channel:
            await interaction.response.send_message(
                "🔊 You must be in a voice channel to use this command.", ephemeral=True
            )
            return None

        guild_id = interaction.guild_id
        assert guild_id is not None
        player = self.players.get(guild_id)

        if player is None:
            voice = await voice_state.channel.connect(self_deaf=True)
            assert interaction.guild is not None
            text_channel = _text_channel(interaction)
            assert text_channel is not None
            queue_dir = self.bot.settings.data_dir / "queues"
            player = GuildPlayer(self, interaction.guild, text_channel, voice, queue_dir)
            self.players[guild_id] = player
            logger.info(
                "Joined voice channel %r in %s", voice_state.channel.name, interaction.guild.name
            )
        elif player.voice.channel != voice_state.channel:
            player.move_to(voice_state.channel)

        text_channel = _text_channel(interaction)
        if text_channel is not None:
            player.text_channel = text_channel
        return player

    @staticmethod
    async def announce_now_playing(player: GuildPlayer) -> None:
        if player.current is None:
            return
        if player.now_view:
            player.now_view.stop()
        embed = _now_playing_embed(player.current, player.queue, player.loop_mode)
        view = NowPlayingView(player)
        try:
            if player.now_message is not None:
                player.now_message = await player.now_message.edit(embed=embed, view=view)
            else:
                player.now_message = await player.text_channel.send(embed=embed, view=view)
        except discord.HTTPException:
            player.now_message = None
            player.now_view = None
            return
        player.now_view = view

    @app_commands.command(name="join", description="➕ Joins your voice channel.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def join(self, interaction: discord.Interaction) -> None:
        player = await self._get_player(interaction)
        if player and player.voice.channel:
            await interaction.response.send_message(f"✅ Joined {player.voice.channel.name}")

    @app_commands.command(
        name="leave", description="🚪 Leaves the voice channel and clears the queue."
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("📴 I'm not in a voice channel.", ephemeral=True)
            return
        await self.destroy_player(interaction.guild)
        await interaction.response.send_message("✅ Left the voice channel.")

    @app_commands.command(
        name="play",
        description="▶️ Play music from YouTube. Supports URLs, playlists, or search queries.",
    )
    @app_commands.describe(
        query="YouTube URL, playlist URL, or search query",
        front="Play this next, before the rest of the queue",
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def play(
        self, interaction: discord.Interaction, query: str, front: bool = False
    ) -> None:
        query = query.strip()
        if not query:
            await interaction.response.send_message("❌ Query cannot be empty.", ephemeral=True)
            return
        if len(query) > 500:
            await interaction.response.send_message(
                "❌ Query too long (max 500 characters).", ephemeral=True
            )
            return

        player = await self._get_player(interaction)
        if player is None:
            return
        await interaction.response.defer()

        if len(player.queue) >= self.max_queue:
            await interaction.followup.send(
                f"📛 Queue is full! Limit {self.max_queue}.", ephemeral=True
            )
            return

        try:
            if query.startswith(("http://", "https://")):
                if "list=" in query:
                    await self._play_playlist(interaction, player, query, front=front)
                else:
                    track = await self.bot.youtube.track(query)
                    await self._enqueue(interaction, player, [track], front=front)
            else:
                await self._play_search(interaction, player, query, front=front)
        except YouTubeError as exc:
            logger.warning("Play failed for %r: %s", query, exc)
            await interaction.followup.send("❌ Could not fetch that track.", ephemeral=True)
        except Exception:
            logger.exception("Error in play command")
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", ephemeral=True
            )

    async def _play_search(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        query: str,
        *,
        front: bool = False,
    ) -> None:
        results = await self.bot.youtube.search(query)
        if not results:
            await interaction.followup.send("🔍 No results found for your query.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔍 Search Results",
            description="Select a track to play:",
            color=EMBED_COLOR,
        )
        for index, track in enumerate(results, start=1):
            duration = f" (`{track.formatted_duration}`)" if track.formatted_duration else ""
            embed.add_field(name=f"{index}. {track.title[:80]}{duration}", value="\u200b", inline=False)
        embed.set_footer(text="Selection will timeout in 60 seconds")

        view = TrackSelectionView(
            results, interaction.user.id, timeout=self.search_timeout
        )
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        if view.selected is None:
            return
        await self._enqueue(interaction, player, [view.selected], front=front)

    async def _play_playlist(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        playlist_url: str,
        *,
        front: bool = False,
    ) -> None:
        tracks = await self.bot.youtube.playlist(playlist_url)
        if not tracks:
            await interaction.followup.send(
                "ℹ️ Playlist is empty or unavailable.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📜 Playlist Selection",
            description=f"Found {len(tracks)} tracks in playlist.\n\nSelect which tracks to add:",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="Options",
            value="• **Add All** - Add all tracks\n• **Custom Selection** - Choose specific tracks or ranges",
            inline=False,
        )
        embed.set_footer(text="Selection will timeout in 60 seconds")

        view = PlaylistSelectionView(
            len(tracks), interaction.user.id, timeout=self.search_timeout
        )
        view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()

        selection = view.selection
        if not selection or selection == "cancel":
            return

        if selection == "all":
            indices = set(range(1, len(tracks) + 1))
        else:
            indices = parse_selection(selection, len(tracks))
            if not indices:
                await interaction.followup.send("❌ Invalid selection format.", ephemeral=True)
                return

        selected = [tracks[index - 1] for index in sorted(indices)]
        if front:
            selected.reverse()
        await self._enqueue(interaction, player, selected, front=front, bulk=True)

    async def _enqueue(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        tracks: list[Track],
        *,
        front: bool = False,
        bulk: bool = False,
    ) -> None:
        added = await player.enqueue(tracks, front=front)
        if added == 0:
            await interaction.followup.send(
                f"📛 Queue is full! Limit {self.max_queue}.", ephemeral=True
            )
            return

        restore_note = ""
        if player.restored:
            restore_note = f"\n♻️ Restored {player.restored} track(s) from the last session"
            player.restored = 0

        if bulk:
            skipped = len(tracks) - added
            message = f"✅ Added {added} track(s) from playlist"
            if skipped:
                message += f" (queue full, {skipped} skipped)"
            await interaction.followup.send(message + restore_note, ephemeral=True)
        else:
            track = tracks[0]
            if player.is_active:
                position = 1 if front else len(player.queue)
                label = "Playing next" if front else "Added to queue"
                await interaction.followup.send(
                    f"➕ {label} (#{position}): **{track.title}**{restore_note}",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"▶️ Starting: **{track.title}**{restore_note}", ephemeral=True
                )

    @app_commands.command(name="skip", description="⏭️ Skip tracks by index or range.")
    @app_commands.describe(query="Index or range to skip (e.g. '1', '0' current track, '1-3')")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def skip(
        self, interaction: discord.Interaction, query: str | None = None
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or (player.current is None and not player.queue):
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return

        indices: set[int]
        if not query:
            indices = {0}
        else:
            try:
                if "-" in query:
                    start_raw, _, end_raw = query.partition("-")
                    start, end = int(start_raw), int(end_raw)
                    if start > end or start < 0:
                        await interaction.response.send_message(
                            "❌ Invalid range.", ephemeral=True
                        )
                        return
                    indices = set(range(start, end + 1))
                else:
                    indices = {int(query)}
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid number format. Use integers like '0' or ranges like '1-3'.",
                    ephemeral=True,
                )
                return

        skipped: list[Track] = []
        if 0 in indices and player.current is not None:
            track = player.stop_current()
            if track:
                skipped.append(track)

        queued = list(player.queue)
        remove = {i for i in indices if 1 <= i <= len(queued)}
        for index in remove:
            skipped.append(queued[index - 1])
        if remove:
            player.queue.clear()
            player.queue.extend(t for i, t in enumerate(queued, start=1) if i not in remove)
            player.save_queue()

        if not skipped:
            await interaction.response.send_message(
                "ℹ️ No tracks were skipped.", ephemeral=True
            )
            return

        if 0 in indices:
            if player.now_message:
                with contextlib.suppress(discord.HTTPException):
                    await player.now_message.edit(
                        content="⏭️ Skipped.", embed=None, view=None
                    )
                player.now_message = None
            player.kick()
        logger.info("Skipped: %s", ", ".join(t.title for t in skipped))
        await interaction.response.send_message(f"⏭ Skipped {len(skipped)} track(s)")

    @app_commands.command(name="queue", description="📜 Show the current queue.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or not player.queue:
            await interaction.response.send_message("ℹ️ The queue is empty.")
            return

        queue_list = "\n".join(
            f"**{index}.** [{track.title[:50]}]({track.page_url})"
            for index, track in enumerate(itertools.islice(player.queue, 10), start=1)
        )
        embed = discord.Embed(
            title=f"📜 Queue ({len(player.queue)} tracks) • Loop: {player.loop_mode}",
            description=queue_list,
            color=EMBED_COLOR,
        )
        if player.current:
            embed.add_field(
                name="Now Playing",
                value=f"[{player.current.title}]({player.current.page_url})",
                inline=False,
            )
        if len(player.queue) > 10:
            embed.set_footer(text=f"... and {len(player.queue) - 10} more tracks")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="current", description="🎵 Show the currently playing track.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def current(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or not player.current:
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=_now_playing_embed(player.current, player.queue)
        )

    @app_commands.command(name="pause", description="⏸️ Pause the current track.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or not player.voice.is_playing():
            await interaction.response.send_message("🔇 Nothing is playing.", ephemeral=True)
            return
        player.voice.pause()
        await interaction.response.send_message("⏸️ Playback paused.")

    @app_commands.command(name="resume", description="▶️ Resume playback.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or not player.voice.is_paused():
            await interaction.response.send_message(
                "ℹ️ Playback is not paused.", ephemeral=True
            )
            return
        player.voice.resume()
        await interaction.response.send_message("▶️ Playback resumed.")

    @app_commands.command(
        name="volume", description="🔊 Set playback volume percent (0-150)."
    )
    @app_commands.describe(percent="Volume percent, 100 is normal loudness (default 75)")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 150]
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return
        applied = player.set_volume(percent / 100)
        if player.now_view:
            player.now_view._sync_buttons()
            with contextlib.suppress(discord.HTTPException):
                await player.now_message.edit(view=player.now_view)
        await interaction.response.send_message(
            f"🔊 Volume set to {round(applied * 100)}%", ephemeral=True
        )

    @app_commands.command(
        name="loop",
        description="🔁 Loop the current track, the whole queue, or nothing.",
    )
    @app_commands.describe(mode="Loop mode (cycles off → track → queue if omitted)")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off", value="off"),
            app_commands.Choice(name="Track", value="track"),
            app_commands.Choice(name="Queue", value="queue"),
        ]
    )
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def loop(
        self, interaction: discord.Interaction, mode: app_commands.Choice[str] | None = None
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return
        new_mode = mode.value if mode else player.cycle_loop()
        if new_mode not in LOOP_MODES:
            await interaction.response.send_message("❌ Invalid loop mode.", ephemeral=True)
            return
        player.loop_mode = new_mode
        player.save_queue()
        emoji = {"off": "▶️", "track": "🔁", "queue": "🔄"}[new_mode]
        await interaction.response.send_message(f"{emoji} Loop mode: **{new_mode}**")

    @app_commands.command(name="shuffle", description="🔀 Shuffle the current queue.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or not player.queue:
            await interaction.response.send_message(
                "ℹ️ The queue is empty, nothing to shuffle.", ephemeral=True
            )
            return
        random.shuffle(player.queue)
        await interaction.response.send_message("🔀 Queue is shuffled.")

    @app_commands.command(name="clear", description="🧹 Clear the queue.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or not player.queue:
            await interaction.response.send_message(
                "ℹ️ The queue is already empty.", ephemeral=True
            )
            return
        player.clear_queue()
        await interaction.response.send_message("🗑️ Queue cleared.")

    @app_commands.command(name="lyrics", description="📝 Get lyrics for a song.")
    @app_commands.describe(query="Song name to search lyrics for (default: current track)")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def lyrics(self, interaction: discord.Interaction, query: str | None = None) -> None:
        if not self.bot.lyrics.enabled:
            await interaction.response.send_message(
                "❌ Lyrics are not configured (missing GENIUS_API_KEY).", ephemeral=True
            )
            return

        if not query:
            player = self.players.get(interaction.guild_id)
            if player and player.current:
                query = player.current.title
            else:
                await interaction.response.send_message(
                    "🔇 No track is playing and no query provided.", ephemeral=True
                )
                return

        await interaction.response.defer()
        try:
            fetched = await self.bot.lyrics.fetch(query)
        except LyricsError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return

        safe_name = re.sub(r"[^\w\-. ]", "", fetched.title).strip()[:64] or "lyrics"
        data = io.BytesIO(fetched.text.encode("utf-8"))
        file = discord.File(data, filename=f"{safe_name}.txt")
        embed = discord.Embed(
            title=f"🎵 {fetched.title}",
            description=f"[Lyrics page]({fetched.url})",
            color=EMBED_COLOR,
        )
        await interaction.followup.send(embed=embed, file=file)


def _now_playing_embed(track: Track, queue: deque[Track], loop_mode: str = "off") -> discord.Embed:
    loop_badge = {"track": "🔁", "queue": "🔄"}.get(loop_mode)
    title = "🎶 Now Playing" + (f" {loop_badge}" if loop_badge else "")
    embed = discord.Embed(
        title=title,
        description=f"[{track.title}]({track.page_url})",
        color=EMBED_COLOR,
    )
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)
    if track.author:
        author_value = (
            f"[{track.author}]({track.author_url})" if track.author_url else track.author
        )
        embed.add_field(name="Author", value=author_value, inline=True)
    if track.formatted_duration:
        embed.add_field(name="Duration", value=track.formatted_duration, inline=True)
    if queue:
        embed.add_field(name="Next Up", value=f"[{queue[0].title}]({queue[0].page_url})", inline=True)
    return embed


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(MusicCog(bot))
