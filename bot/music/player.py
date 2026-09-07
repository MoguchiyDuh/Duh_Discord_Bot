from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from pathlib import Path
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

LOOP_MODES = ("off", "track", "queue")


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
        queue_dir: Path,
    ) -> None:
        self.cog = cog
        self.guild = guild
        self.text_channel = text_channel
        self.voice = voice
        self.queue: deque[Track] = deque()
        self.current: Track | None = None
        self.loop_mode: str = "off"
        self.now_message: discord.Message | None = None
        self.now_view: discord.ui.View | None = None
        self.restored = 0
        self._lock = asyncio.Lock()
        self._session = 0
        self._stopping = False
        self._idle_task: asyncio.Task[None] | None = None
        self._advance_task: asyncio.Task[None] | None = None
        self._queue_file = queue_dir / f"{guild.id}.json"
        self._load_queue()

    @property
    def is_active(self) -> bool:
        return bool(self.voice.is_playing() or self.voice.is_paused())

    def move_to(self, channel: discord.abc.Connectable) -> None:
        self.voice.move_to(channel)

    async def enqueue(self, tracks: list[Track], *, front: bool = False) -> int:
        added: list[Track] = []
        for track in tracks:
            if len(self.queue) >= self.cog.max_queue:
                break
            if front:
                self.queue.appendleft(track)
            else:
                self.queue.append(track)
            added.append(track)
        if added:
            self.save_queue()
            if not self.is_active:
                self.kick()
        return len(added)

    def clear_queue(self) -> None:
        self.queue.clear()
        with contextlib.suppress(OSError):
            self._queue_file.unlink(missing_ok=True)

    def cycle_loop(self) -> str:
        index = LOOP_MODES.index(self.loop_mode)
        self.loop_mode = LOOP_MODES[(index + 1) % len(LOOP_MODES)]
        self.save_queue()
        return self.loop_mode

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
                if self.loop_mode == "track" and self.current is not None:
                    track = self.current
                elif self.queue:
                    track = self.queue.popleft()
                    self.save_queue()
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
                if self.loop_mode == "queue" and self.current is not None:
                    self.queue.append(self.current)
                    self.save_queue()
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
        if self.now_view:
            self.now_view.stop()
        if self.now_message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.now_message.delete()
            self.now_message = None
        if self.current is not None:
            self.queue.appendleft(self.current)
            self.current = None
            self.save_queue()
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

    def _load_queue(self) -> None:
        try:
            data = json.loads(self._queue_file.read_text("utf-8"))
            tracks = [Track.from_dict(entry) for entry in data.get("queue", [])]
        except (OSError, ValueError, KeyError, TypeError):
            return
        self.queue.extend(tracks[: self.cog.max_queue])
        if data.get("loop") in LOOP_MODES:
            self.loop_mode = data["loop"]
        self.restored = len(self.queue)
        if self.restored:
            logger.info("Restored %d queued track(s) for %s", self.restored, self.guild.name)

    def save_queue(self) -> None:
        payload = {"loop": self.loop_mode, "queue": [t.to_dict() for t in self.queue]}
        try:
            self._queue_file.parent.mkdir(parents=True, exist_ok=True)
            self._queue_file.write_text(
                json.dumps(payload, ensure_ascii=False), "utf-8"
            )
        except OSError:
            logger.exception("Failed to persist queue for %s", self.guild.name)

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
