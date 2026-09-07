from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from typing import TYPE_CHECKING

import discord

from bot.services.youtube import Track

if TYPE_CHECKING:
    from bot.cogs.music import MusicCog

logger = logging.getLogger(__name__)

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

MAX_CONSECUTIVE_FAILURES = 5


def _consume_future(future: asyncio.Future[None]) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        future.exception()


class GuildPlayer:
    def __init__(
        self,
        cog: MusicCog,
        guild: discord.Guild,
        text_channel: discord.abc.Messageable,
        voice: discord.VoiceClient,
    ) -> None:
        self.cog = cog
        self.guild = guild
        self.text_channel = text_channel
        self.voice = voice
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.loop = False
        self._lock = asyncio.Lock()
        self._session = 0
        self._stopping = False
        self._idle_task: asyncio.Task[None] | None = None
        self._advance_task: asyncio.Task[None] | None = None

    @property
    def is_active(self) -> bool:
        return bool(self.voice.is_playing() or self.voice.is_paused())

    def move_to(self, channel: discord.abc.Connectable) -> None:
        self.voice.move_to(channel)

    async def enqueue(self, tracks: list[Track]) -> int:
        added = 0
        for track in tracks:
            if len(self.queue) >= self.cog.max_queue:
                break
            self.queue.append(track)
            added += 1
        if added and not self.is_active:
            self.kick()
        return added

    def kick(self) -> None:
        self._cancel_idle()
        if self._advance_task is None or self._advance_task.done():
            self._advance_task = asyncio.create_task(self.advance())

    def stop_current(self) -> Track | None:
        track = self.current
        self.current = None
        self._session += 1
        if self.is_active:
            self.voice.stop()
        return track

    async def advance(self) -> None:
        async with self._lock:
            if self._stopping or self.is_active:
                return
            self._cancel_idle()
            failures = 0
            while not self._stopping and not self.is_active:
                if self.loop and self.current is not None:
                    track = self.current
                elif self.queue:
                    track = self.queue.popleft()
                else:
                    self.current = None
                    self._schedule_idle()
                    return

                self.current = track
                try:
                    async with asyncio.timeout(self.cog.resolve_timeout):
                        stream_url = await self.cog.youtube.stream_url(track.page_url)
                        source = await discord.FFmpegOpusAudio.from_probe(
                            stream_url, **FFMPEG_OPTIONS
                        )
                except Exception as exc:
                    failures += 1
                    logger.warning("Failed to start %r: %s", track.title, exc)
                    self.current = None
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        await self._send(f"❌ {MAX_CONSECUTIVE_FAILURES} tracks failed in a row, stopping.")
                        self._schedule_idle()
                        return
                    await self._send(
                        f"⏭️ Could not play **{track.title}**, skipping ({failures}/{MAX_CONSECUTIVE_FAILURES})."
                    )
                    continue

                self._start_source(source)
                await self.cog.announce_now_playing(self)
                return

    def _start_source(self, source: discord.AudioSource) -> None:
        self._session += 1
        session = self._session

        def _after(error: Exception | None) -> None:
            if error:
                logger.error("Playback error in %s: %s", self.guild.name, error)

            async def _finish() -> None:
                if session != self._session or self._stopping:
                    return
                await self.advance()

            future = asyncio.run_coroutine_threadsafe(_finish(), self.cog.bot.loop)
            future.add_done_callback(_consume_future)

        self.voice.play(source, after=_after)

    async def destroy(self) -> None:
        self._stopping = True
        self._session += 1
        self._cancel_idle()
        if self._advance_task and not self._advance_task.done():
            self._advance_task.cancel()
        try:
            if self.is_active:
                self.voice.stop()
            await asyncio.wait_for(self.voice.disconnect(force=True), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Voice disconnect timeout in %s", self.guild.name)
        except Exception as exc:
            logger.warning("Voice disconnect failed in %s: %s", self.guild.name, exc)
        finally:
            self.queue.clear()
            self.current = None

    def _schedule_idle(self) -> None:
        self._cancel_idle()
        self._idle_task = asyncio.create_task(self._idle_disconnect())

    def _cancel_idle(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    async def _idle_disconnect(self) -> None:
        try:
            await asyncio.sleep(self.cog.idle_timeout)
        except asyncio.CancelledError:
            return
        logger.info("Idle timeout in %s, disconnecting", self.guild.name)
        await self._send("💤 Idle for too long, disconnecting.")
        await self.cog.destroy_player(self.guild)

    async def _send(self, content: str) -> None:
        with contextlib.suppress(discord.HTTPException):
            await self.text_channel.send(content)
