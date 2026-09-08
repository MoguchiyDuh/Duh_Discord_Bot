from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import time
from collections import Counter, deque
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

VOLUME_GAIN = 0.2

MAX_VOLUME = 1.5

LOOP_MODES = ("off", "track", "queue")

HISTORY_LIMIT = 50
EVENT_LIMIT = 5


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
        self.history: deque[Track] = deque(maxlen=HISTORY_LIMIT)
        self.current: Track | None = None
        self.loop_mode: str = "off"
        self.volume: float = cog.default_volume
        self.restored = 0
        self.events: deque[str] = deque(maxlen=EVENT_LIMIT)
        self.tracks_played = 0
        self.listen_seconds = 0.0
        self.adds: Counter[str] = Counter()
        self.skips: Counter[str] = Counter()
        self.page: str = "now"
        self.queue_page = 0
        self.card_message: discord.Message | None = None
        self.card_view: discord.ui.View | None = None
        self.card_dirty = True
        self.last_card_edit = 0.0
        self._position = 0.0
        self._play_started: float | None = None
        self._lock = asyncio.Lock()
        self._session = 0
        self._stopping = False
        self._idle_task: asyncio.Task[None] | None = None
        self._advance_task: asyncio.Task[None] | None = None
        self._queue_file = queue_dir / f"{guild.id}.json"
        self.stale_card: dict | None = None
        self._load_queue()

    @property
    def is_active(self) -> bool:
        return bool(self.voice.is_playing() or self.voice.is_paused())

    @property
    def position(self) -> float:
        if self._play_started is None:
            return self._position
        return self._position + (time.monotonic() - self._play_started)

    def _pause_clock(self) -> None:
        if self._play_started is not None:
            self._position += time.monotonic() - self._play_started
            self._play_started = None

    def _resume_clock(self) -> None:
        if self._play_started is None and self.current is not None:
            self._play_started = time.monotonic()

    def _reset_clock(self) -> None:
        self._position = 0.0
        self._play_started = time.monotonic()

    def touch_card(self) -> None:
        self.card_dirty = True

    def note_event(self, text: str) -> None:
        self.events.append(text)
        self.touch_card()

    def move_to(self, channel: discord.abc.Connectable) -> None:
        self.voice.move_to(channel)

    async def enqueue(
        self, tracks: list[Track], *, front: bool = False, requester: str | None = None
    ) -> int:
        added: list[Track] = []
        for track in tracks:
            if len(self.queue) >= self.cog.max_queue:
                break
            if requester:
                track.requester = requester
            if front:
                self.queue.appendleft(track)
            else:
                self.queue.append(track)
            added.append(track)
        if added:
            if requester:
                self.adds[requester] += len(added)
            self.save_queue()
            self.touch_card()
            if not self.is_active:
                self.kick()
        return len(added)

    def clear_queue(self) -> None:
        self.queue.clear()
        with contextlib.suppress(OSError):
            self._queue_file.unlink(missing_ok=True)
        self.touch_card()

    def set_volume(self, value: float) -> float:
        self.volume = max(0.0, min(value, MAX_VOLUME))
        if self.is_active and isinstance(self.voice.source, discord.PCMVolumeTransformer):
            self.voice.source.volume = self.volume * VOLUME_GAIN
        self.save_queue()
        self.touch_card()
        return self.volume

    def cycle_loop(self) -> str:
        index = LOOP_MODES.index(self.loop_mode)
        self.loop_mode = LOOP_MODES[(index + 1) % len(LOOP_MODES)]
        self.save_queue()
        self.touch_card()
        return self.loop_mode

    def shuffle(self) -> int:
        count = len(self.queue)
        self._shuffle_queue()
        self.touch_card()
        return count

    def _shuffle_queue(self) -> None:
        random.shuffle(self.queue)
        self.save_queue()

    def remove_at(self, index: int) -> Track | None:
        if not 1 <= index <= len(self.queue):
            return None
        track = self.queue[index - 1]
        del self.queue[index - 1]
        self.save_queue()
        self.touch_card()
        return track

    def prev(self) -> Track | None:
        if not self.history:
            return None
        track = self.history.pop()
        if self.current is not None:
            self.queue.appendleft(self.current)
        self.queue.appendleft(track)
        self.save_queue()
        self.touch_card()
        return track

    def kick(self) -> None:
        self._cancel_idle()
        if self._advance_task is None or self._advance_task.done():
            self._advance_task = asyncio.create_task(self.advance())

    def stop_current(self, *, record: bool = True) -> Track | None:
        track = self.current
        if record:
            self._pause_clock()
            self.listen_seconds += self._position
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
                previous = self.current
                if self.loop_mode == "track" and self.current is not None:
                    track = self.current
                elif self.queue:
                    if self.loop_mode == "queue" and previous is not None:
                        self.queue.append(previous)
                        self.save_queue()
                    track = self.queue.popleft()
                    self.save_queue()
                else:
                    self._pause_clock()
                    self.listen_seconds += self._position
                    self.current = None
                    self.touch_card()
                    self._schedule_idle()
                    return

                if previous is not None and previous is not track:
                    self.history.append(previous)
                    self._pause_clock()
                    self.listen_seconds += self._position

                self.current = track
                try:
                    async with asyncio.timeout(self.cog.resolve_timeout):
                        stream_url = await self.cog.bot.youtube.stream_url(track.page_url)
                        pcm = discord.FFmpegPCMAudio(
                            stream_url,
                            before_options=FFMPEG_OPTIONS["before_options"],
                            options=FFMPEG_OPTIONS["options"],
                        )
                        source = discord.PCMVolumeTransformer(
                            pcm, volume=self.volume * VOLUME_GAIN
                        )
                except Exception as exc:
                    failures += 1
                    logger.warning("Failed to start %r: %s", track.title, exc)
                    self.current = None
                    self.note_event(f"⚠️ Failed: {track.title[:40]}")
                    if failures >= MAX_CONSECUTIVE_FAILURES:
                        self.note_event(f"❌ {MAX_CONSECUTIVE_FAILURES} failures in a row, stopping")
                        self._schedule_idle()
                        return
                    continue

                self.tracks_played += 1
                self._reset_clock()
                if self.page == "queue":
                    self.page = "now"
                self.touch_card()
                self._start_source(source)
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
        if self.card_view:
            self.card_view.stop()
            self.card_view = None
        self._pause_clock()
        self.listen_seconds += self._position
        await self.cog.render_tombstone(self)
        self.card_message = None
        if self.current is not None:
            self.queue.appendleft(self.current)
            self.current = None
        if self.is_active:
            with contextlib.suppress(Exception):
                self.voice.stop()
        try:
            await asyncio.wait_for(self.voice.disconnect(force=True), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("Voice disconnect timeout in %s", self.guild.name)
        except Exception as exc:
            logger.warning("Voice disconnect failed in %s: %s", self.guild.name, exc)

    def _load_queue(self) -> None:
        try:
            data = json.loads(self._queue_file.read_text("utf-8"))
            tracks = [Track.from_dict(entry) for entry in data.get("queue", [])]
        except (OSError, ValueError, KeyError, TypeError):
            return
        self.queue.extend(tracks[: self.cog.max_queue])
        if data.get("loop") in LOOP_MODES:
            self.loop_mode = data["loop"]
        volume = data.get("volume")
        if isinstance(volume, (int, float)) and 0.0 <= volume <= MAX_VOLUME:
            self.volume = float(volume)
        card = data.get("card")
        if isinstance(card, dict) and card.get("channel") and card.get("message"):
            self.stale_card = card
        self.restored = len(self.queue)
        if self.restored:
            logger.info("Restored %d queued track(s) for %s", self.restored, self.guild.name)

    def save_queue(self) -> None:
        payload: dict = {
            "loop": self.loop_mode,
            "volume": self.volume,
            "queue": [t.to_dict() for t in self.queue],
        }
        if self.card_message is not None:
            payload["card"] = {
                "channel": self.card_message.channel.id,
                "message": self.card_message.id,
            }
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
        self.note_event("💤 Idle timeout")
        await self.cog.destroy_player(self.guild)
