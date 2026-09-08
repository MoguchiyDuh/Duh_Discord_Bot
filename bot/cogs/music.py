from __future__ import annotations

import contextlib
import io
import logging
import re
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs import EMBED_COLOR, BaseCog, channel_allowed
from bot.music.card import (
    PlayerCardView,
    SearchPickerView,
    render_card,
    render_tombstone,
)
from bot.music.card import format_seconds
from bot.music.player import LOOP_MODES, GuildPlayer
from bot.music.views import PlaylistSelectionView, parse_selection
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

    async def cog_load(self) -> None:
        self.card_loop.start()

    async def cog_unload(self) -> None:
        self.card_loop.cancel()
        for guild_id in list(self.players):
            player = self.players.pop(guild_id, None)
            if player:
                await player.destroy()

    @tasks.loop(seconds=1)
    async def card_loop(self) -> None:
        for player in list(self.players.values()):
            now = time.monotonic()
            progress_due = (
                player.page == "now"
                and player.voice.is_playing()
                and (now - player.last_card_edit) >= 10
            )
            if not (player.card_dirty or progress_due):
                continue
            await self._render_card(player)
            player.card_dirty = False
            player.last_card_edit = now

    async def _render_card(self, player: GuildPlayer) -> None:
        embed = render_card(player)
        try:
            if player.card_message is None:
                if player.card_view is None:
                    player.card_view = PlayerCardView(self, player)
                player.card_view.sync()
                player.card_message = await player.text_channel.send(
                    embed=embed, view=player.card_view, silent=True
                )
                player.save_queue()
            else:
                if player.card_view is not None:
                    player.card_view.sync()
                player.card_message = await player.card_message.edit(
                    embed=embed, view=player.card_view
                )
        except discord.NotFound:
            with contextlib.suppress(discord.HTTPException):
                if player.card_view is None:
                    player.card_view = PlayerCardView(self, player)
                player.card_view.sync()
                player.card_message = await player.text_channel.send(
                    embed=embed, view=player.card_view, silent=True
                )
                player.save_queue()
        except discord.HTTPException as exc:
            logger.warning("Card update failed in %s: %s", player.guild.name, exc)

    async def render_tombstone(self, player: GuildPlayer) -> None:
        message = player.card_message
        player.card_message = None
        player.card_view = None
        if message is None:
            return
        embed = render_tombstone(player)
        with contextlib.suppress(discord.HTTPException):
            await message.edit(embed=embed, view=None, content=None)
        player.save_queue()

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
            voice = interaction.guild.voice_client
            if voice is not None and not voice.is_connected():
                with contextlib.suppress(Exception):
                    await voice.disconnect(force=True)
                voice = None
            if voice is None:
                try:
                    voice = await voice_state.channel.connect(self_deaf=True)
                except discord.ClientException:
                    voice = interaction.guild.voice_client
                    if voice is None:
                        raise
            assert interaction.guild is not None
            text_channel = _text_channel(interaction)
            assert text_channel is not None
            queue_dir = self.bot.settings.data_dir / "queues"
            player = GuildPlayer(self, interaction.guild, text_channel, voice, queue_dir)
            self.players[guild_id] = player
            await self._tombstone_stale_card(player)
            logger.info(
                "Joined voice channel %r in %s", voice_state.channel.name, interaction.guild.name
            )
        elif player.voice.channel != voice_state.channel:
            player.move_to(voice_state.channel)

        text_channel = _text_channel(interaction)
        if text_channel is not None and player.card_message is None:
            player.text_channel = text_channel
        return player

    async def _tombstone_stale_card(self, player: GuildPlayer) -> None:
        stale = player.stale_card
        player.stale_card = None
        if not stale:
            return
        channel = self.bot.get_channel(stale["channel"])
        if not isinstance(channel, discord.abc.Messageable):
            return
        try:
            message = await channel.fetch_message(stale["message"])
        except discord.HTTPException:
            return
        embed = discord.Embed(
            title="🏁 Previous session ended (bot restarted)",
            color=discord.Color.dark_grey(),
        )
        with contextlib.suppress(discord.HTTPException):
            await message.edit(embed=embed, view=None, content=None)

    async def act_enqueue(
        self,
        interaction: discord.Interaction | None,
        player: GuildPlayer,
        tracks: list[Track],
        *,
        front: bool = False,
        requester: str | None = None,
        bulk: bool = False,
    ) -> int:
        added = await player.enqueue(tracks, front=front, requester=requester)
        if added == 0:
            if interaction:
                await interaction.followup.send(
                    f"📛 Queue is full! Limit {self.max_queue}.", ephemeral=True
                )
            return 0

        if requester:
            if bulk:
                player.note_event(f"➕ {requester} added {added} tracks")
            elif front:
                player.note_event(f"⏭️ {requester} queued {tracks[0].title[:40]} (next)")
            else:
                player.note_event(f"➕ {requester} added {tracks[0].title[:40]}")

        if interaction:
            if bulk:
                skipped = len(tracks) - added
                message = f"✅ Added {added} track(s) from playlist"
                if skipped:
                    message += f" (queue full, {skipped} skipped)"
                await interaction.followup.send(message, ephemeral=True)
            else:
                track = tracks[0]
                if not player.is_active and player.current is None:
                    label, icon = "Starting", "▶️"
                elif front:
                    label, icon = "Playing next", "⏭️"
                else:
                    label, icon = f"Added to queue (#{len(player.queue)})", "➕"
                await interaction.followup.send(
                    f"{icon} {label}: **{track.title}**",
                    ephemeral=True,
                )
        return added

    async def act_add(
        self,
        interaction: discord.Interaction,
        player: GuildPlayer,
        query: str,
        *,
        front: bool = False,
    ) -> None:
        if len(player.queue) >= self.max_queue:
            await interaction.followup.send(
                f"📛 Queue is full! Limit {self.max_queue}.", ephemeral=True
            )
            return
        requester = interaction.user.display_name
        try:
            if query.startswith(("http://", "https://")):
                if "list=" in query:
                    tracks = await self.bot.youtube.playlist(query)
                    if not tracks:
                        await interaction.followup.send(
                            "ℹ️ Playlist is empty or unavailable.", ephemeral=True
                        )
                        return
                    if "list=RD" in query:
                        player.start_mix(query, tracks)
                        await self.act_enqueue(
                            interaction,
                            player,
                            tracks,
                            front=front,
                            requester=requester,
                            bulk=True,
                        )
                        return
                    view = PlaylistSelectionView(
                        len(tracks), interaction.user.id, timeout=self.search_timeout
                    )
                    view.message = await interaction.followup.send(
                        embed=_playlist_embed(tracks), view=view, ephemeral=True
                    )
                    await view.wait()
                    selection = view.selection
                    if not selection or selection == "cancel":
                        return
                    if selection == "all":
                        indices = set(range(1, len(tracks) + 1))
                    else:
                        indices = parse_selection(selection, len(tracks))
                        if not indices:
                            await interaction.followup.send(
                                "❌ Invalid selection format.", ephemeral=True
                            )
                            return
                    selected = [tracks[i - 1] for i in sorted(indices)]
                    if front:
                        selected.reverse()
                    await self.act_enqueue(
                        interaction, player, selected, front=front, requester=requester, bulk=True
                    )
                else:
                    track = await self.bot.youtube.track(query)
                    await self.act_enqueue(
                        interaction, player, [track], front=front, requester=requester
                    )
            elif query.lower().startswith("sc:"):
                results = await self.bot.youtube.search_soundcloud(query[3:].strip())
                if not results:
                    await interaction.followup.send(
                        "🔍 No SoundCloud results found.", ephemeral=True
                    )
                    return
                picker = SearchPickerView(
                    self, player, results, requester, timeout=self.search_timeout
                )
                await interaction.followup.send(
                    embed=_picker_embed(results, f"sc: {query[3:]}"), view=picker, ephemeral=True
                )
                picker.message = await interaction.original_response()
                await picker.wait()
            else:
                results = await self.bot.youtube.search(query)
                if not results:
                    await interaction.followup.send(
                        "🔍 No results found for your query.", ephemeral=True
                    )
                    return
                picker = SearchPickerView(
                    self, player, results, requester, timeout=self.search_timeout
                )
                await interaction.followup.send(
                    embed=_picker_embed(results, query), view=picker, ephemeral=True
                )
                picker.message = await interaction.original_response()
                await picker.wait()
        except YouTubeError as exc:
            logger.warning("Add failed for %r: %s", query, exc)
            await interaction.followup.send("❌ Could not fetch that track.", ephemeral=True)
        except Exception:
            logger.exception("Error adding track %r", query)
            await interaction.followup.send(
                "❌ An error occurred while processing your request.", ephemeral=True
            )

    async def act_play_pause(self, player: GuildPlayer, name: str) -> str | None:
        if player.voice.is_playing():
            player.voice.pause()
            player._pause_clock()
            player.note_event(f"⏸️ Paused ({name})")
            return None
        if player.voice.is_paused():
            player.voice.resume()
            player._resume_clock()
            player.note_event(f"▶️ Resumed ({name})")
            return None
        return "Nothing is playing."

    async def act_skip(self, player: GuildPlayer, name: str) -> str | None:
        if player.current is None and not player.queue:
            return "Nothing is playing."
        track = player.stop_current() if player.current is not None else None
        if track is not None:
            player.history.append(track)
            player.skips[name] += 1
            player.note_event(f"⏭️ {name} skipped {track.title[:40]}")
        else:
            player.note_event(f"⏭️ {name} skipped ahead")
        player.kick()
        return None

    async def act_prev(self, player: GuildPlayer, name: str) -> str | None:
        track = player.prev()
        if track is None:
            return "No history yet."
        player.stop_current(record=False)
        player.note_event(f"⏮️ {name} went back to {track.title[:40]}")
        player.kick()
        return None

    async def act_shuffle(self, player: GuildPlayer, name: str) -> str | None:
        if not player.queue:
            return "The queue is empty, nothing to shuffle."
        count = player.shuffle()
        player.note_event(f"🔀 {name} shuffled {count} tracks")
        return None

    async def act_stop(self, player: GuildPlayer, name: str) -> None:
        player.note_event(f"⏹️ {name} stopped the session")
        await self.destroy_player(player.guild)

    async def act_volume(self, player: GuildPlayer, name: str, percent: int) -> int:
        applied = player.set_volume(percent / 100)
        player.note_event(f"🔊 {name} set volume to {round(applied * 100)}%")
        return round(applied * 100)

    async def act_seek(self, player: GuildPlayer, name: str, delta: float) -> str | None:
        if player.current is None or not player.is_active:
            return "Nothing is playing."
        target = player.position + delta
        applied = player.request_seek(target)
        direction = "⏩" if delta > 0 else "⏪"
        player.note_event(
            f"{direction} {name} seeked to {format_seconds(applied)}"
        )
        return None

    async def act_lyrics(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        query = player.current.title if player and player.current else None
        if not query:
            await interaction.followup.send(
                "🔇 No track is playing and no query provided.", ephemeral=True
            )
            return
        if not self.bot.lyrics.enabled:
            await interaction.followup.send(
                "❌ Lyrics are not configured (missing GENIUS_API_KEY).", ephemeral=True
            )
            return
        try:
            fetched = await self.bot.lyrics.fetch(query)
        except LyricsError as exc:
            await interaction.followup.send(f"❌ {exc}", ephemeral=True)
            return
        safe_name = re.sub(r"[^\w\-. ]", "", fetched.title).strip()[:64] or "lyrics"
        data = io.BytesIO(fetched.text.encode("utf-8"))
        await interaction.followup.send(file=discord.File(data, filename=f"{safe_name}.txt"))

    @app_commands.command(name="join", description="➕ Joins your voice channel.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def join(self, interaction: discord.Interaction) -> None:
        player = await self._get_player(interaction)
        if player and player.voice.channel:
            await interaction.response.send_message(
                f"✅ Joined {player.voice.channel.name}", ephemeral=True
            )

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
        if player.card_message:
            player.note_event(f"🚪 {interaction.user.display_name} left the session")
        await self.destroy_player(interaction.guild)
        await interaction.response.send_message("✅ Left the voice channel.", ephemeral=True)

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
        await interaction.response.defer(ephemeral=True)
        await self.act_add(interaction, player, query, front=front)

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
                player.history.append(track)
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
            player.note_event(
                f"⏭️ {interaction.user.display_name} skipped {skipped[0].title[:40]}"
            )
            player.kick()
        else:
            player.touch_card()
        logger.info("Skipped: %s", ", ".join(t.title for t in skipped))
        await interaction.response.send_message(
            f"⏭ Skipped {len(skipped)} track(s)", ephemeral=True
        )

    @app_commands.command(
        name="seek", description="⏩ Jump to a position in the current track."
    )
    @app_commands.describe(seconds="Target position in seconds (e.g. 90 for 1:30)")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def seek(
        self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 7200]
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if not player or player.current is None:
            await interaction.response.send_message("🔇 Nothing is playing.", ephemeral=True)
            return
        applied = player.request_seek(float(seconds))
        player.note_event(
            f"⏩ {interaction.user.display_name} seeked to {format_seconds(applied)}"
        )
        await interaction.response.send_message(
            f"⏩ Seeked to {format_seconds(applied)}", ephemeral=True
        )

    @app_commands.command(name="queue", description="📜 Show the queue on the card.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("📴 I'm not in a voice channel.", ephemeral=True)
            return
        player.page = "queue"
        player.touch_card()
        await interaction.response.send_message(
            "📜 Queue shown on the card.", ephemeral=True
        )

    @app_commands.command(name="current", description="🎵 Show the now-playing card.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def current(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("📴 I'm not in a voice channel.", ephemeral=True)
            return
        player.page = "now"
        player.touch_card()
        await interaction.response.send_message(
            "🎵 Now playing shown on the card.", ephemeral=True
        )

    @app_commands.command(name="pause", description="⏸️ Pause the current track.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return
        error = await self.act_play_pause(player, interaction.user.display_name)
        if error:
            await interaction.response.send_message(f"ℹ️ {error}", ephemeral=True)
        else:
            await interaction.response.send_message("⏸️ Paused.", ephemeral=True)

    @app_commands.command(name="resume", description="▶️ Resume playback.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return
        error = await self.act_play_pause(player, interaction.user.display_name)
        if error:
            await interaction.response.send_message(f"ℹ️ {error}", ephemeral=True)
        else:
            await interaction.response.send_message("▶️ Resumed.", ephemeral=True)

    @app_commands.command(
        name="volume", description="🔊 Set playback volume percent (0-150)."
    )
    @app_commands.describe(percent="Volume percent, 100 is normal loudness")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 150]
    ) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("🔇 I'm not playing anything.", ephemeral=True)
            return
        applied = await self.act_volume(player, interaction.user.display_name, percent)
        await interaction.response.send_message(f"🔊 Volume set to {applied}%", ephemeral=True)

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
        player.note_event(
            f"🔁 {interaction.user.display_name} set loop to {new_mode}"
        )
        await interaction.response.send_message(f"🔁 Loop mode: **{new_mode}**", ephemeral=True)

    @app_commands.command(name="shuffle", description="🔀 Shuffle the current queue.")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.players.get(interaction.guild_id)
        if not player:
            await interaction.response.send_message("📴 I'm not in a voice channel.", ephemeral=True)
            return
        error = await self.act_shuffle(player, interaction.user.display_name)
        if error:
            await interaction.response.send_message(f"ℹ️ {error}", ephemeral=True)
        else:
            await interaction.response.send_message("🔀 Queue is shuffled.", ephemeral=True)

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
        player.note_event(f"🧹 {interaction.user.display_name} cleared the queue")
        await interaction.response.send_message("🗑️ Queue cleared.", ephemeral=True)

    @app_commands.command(name="lyrics", description="📝 Get lyrics for a song.")
    @app_commands.describe(query="Song name to search lyrics for (default: current track)")
    @channel_allowed(__file__)
    @app_commands.guild_only()
    async def lyrics(self, interaction: discord.Interaction, query: str | None = None) -> None:
        if not query:
            player = self.players.get(interaction.guild_id)
            if player and player.current:
                query = player.current.title
            else:
                await interaction.response.send_message(
                    "🔇 No track is playing and no query provided.", ephemeral=True
                )
                return
        if not self.bot.lyrics.enabled:
            await interaction.response.send_message(
                "❌ Lyrics are not configured (missing GENIUS_API_KEY).", ephemeral=True
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
        await interaction.followup.send(file=discord.File(data, filename=f"{safe_name}.txt"))


def _picker_embed(results: list[Track], query: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"🔍 Results for “{query[:60]}”",
        description="Pick a track from the menu below.",
        color=EMBED_COLOR,
    )
    embed.set_footer(text="Selection will timeout in 60 seconds")
    return embed


def _playlist_embed(tracks: list[Track]) -> discord.Embed:
    total = sum(t.duration or 0 for t in tracks)
    embed = discord.Embed(
        title="📜 Playlist Selection",
        description=(
            f"Found {len(tracks)} tracks • {format_seconds(total)} total.\n\n"
            "Select which tracks to add:"
        ),
        color=EMBED_COLOR,
    )
    embed.add_field(
        name="Options",
        value="• **Add All** - Add all tracks\n• **Custom Selection** - Choose specific tracks or ranges",
        inline=False,
    )
    embed.set_footer(text="Selection will timeout in 60 seconds")
    return embed


async def setup(bot: DuhBot) -> None:
    await bot.add_cog(MusicCog(bot))
