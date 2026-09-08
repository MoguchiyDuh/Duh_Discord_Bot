from __future__ import annotations

import asyncio
import collections
import contextlib
import os
from pathlib import Path
from typing import Callable

import pytest
import pytest_asyncio

os.environ.setdefault("DISCORD_TOKEN", "dummy")

import discord

from bot.music.player import GuildPlayer
from bot.services.youtube import Track


class FakeAudioSource(discord.AudioSource):
    def read(self) -> bytes:
        return b""

    def is_opus(self) -> bool:
        return False


class FakeVoice:
    def __init__(self) -> None:
        self.source: object | None = None
        self.playing = False
        self.finish_delay: float | None = None
        self.started: list[str] = []
        self.channel: object | None = None

    def is_playing(self) -> bool:
        return self.playing

    def is_paused(self) -> bool:
        return bool(self.source and not self.playing)

    def is_connected(self) -> bool:
        return True

    def stop(self) -> None:
        self.source = None
        self.playing = False

    def play(self, source: object, after: Callable[[Exception | None], None] | None = None) -> None:
        self.source = source
        self.playing = True
        self.started.append(type(source.original).__name__)

        def _finish() -> None:
            self.playing = False
            self.source = None
            if after is not None:
                after(None)

        if after is not None and self.finish_delay is not None:
            asyncio.get_running_loop().call_later(self.finish_delay, _finish)

    def pause(self) -> None:
        self.playing = False

    def resume(self) -> None:
        self.playing = True


class FakeYouTube:
    def __init__(self) -> None:
        self.batches: list[list[Track]] = []
        self.playlist_calls = 0

    async def resolve(self, page_url: str) -> tuple[str, int]:
        return f"https://stream/{page_url}", 100

    async def playlist(self, url: str) -> list[Track]:
        self.playlist_calls += 1
        if not self.batches:
            return []
        return self.batches.pop(0)


class FakeBot:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.youtube = FakeYouTube()
        self.loop = loop


class FakeChannelStatic:
    id = 999


class FakeMessage:
    def __init__(self, id: int) -> None:
        self.id = id
        self.channel = FakeChannelStatic()
        self.edits: list[dict] = []

    async def edit(self, **kwargs: object) -> "FakeMessage":
        self.edits.append(kwargs)
        return self


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, **kwargs: object) -> FakeMessage:
        self.sent.append(kwargs)
        return FakeMessage(len(self.sent))


class FakeCog:
    def __init__(self, loop: asyncio.AbstractEventLoop, *, max_queue: int, default_volume: float) -> None:
        self.bot = FakeBot(loop)
        self.max_queue = max_queue
        self.resolve_timeout = 5
        self.idle_timeout = 300
        self.default_volume = default_volume
        self.tombstones = 0

    async def render_tombstone(self, player: GuildPlayer) -> None:
        self.tombstones += 1

    async def destroy_player(self, guild: object) -> None:
        pass


class FakeGuild:
    id = 1
    name = "g"


def make_track(title: str, duration: int | None = 100) -> Track:
    return Track(f"https://www.youtube.com/watch?v={title}", title, duration)


async def await_until(
    condition: Callable[[], bool], timeout: float = 2.0, interval: float = 0.02
) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if condition():
            return True
        await asyncio.sleep(interval)
    return condition()


def _build_player(
    loop: asyncio.AbstractEventLoop | None,
    queue_file: Path,
    *,
    max_queue: int,
    default_volume: float,
    with_channel: bool,
) -> GuildPlayer:
    p = object.__new__(GuildPlayer)
    p.cog = FakeCog(loop, max_queue=max_queue, default_volume=default_volume)
    p.guild = FakeGuild()
    p.text_channel = FakeChannel() if with_channel else None
    p.voice = FakeVoice()
    p.queue = collections.deque()
    p.history = collections.deque(maxlen=50)
    p.current = None
    p.loop_mode = "off"
    p.volume = default_volume
    p.restored = 0
    p.events = collections.deque(maxlen=5)
    p.tracks_played = 0
    p.listen_seconds = 0.0
    p.adds = collections.Counter()
    p.skips = collections.Counter()
    p.page = "now"
    p.queue_page = 0
    p.history_page = 0
    p.card_message = None
    p.card_view = None
    p.card_dirty = True
    p.last_card_edit = 0.0
    p._position = 0.0
    p._play_started = None
    p._seek_target = None
    p.mix_url = None
    p._mix_loading = False
    p._mix_seen = set()
    p._mix_task = None
    p._mix_misses = 0
    p._lock = asyncio.Lock()
    p._session = 0
    p._stopping = False
    p._idle_task = None
    p._advance_task = None
    p._queue_file = queue_file
    p.stale_card = None
    return p


@pytest_asyncio.fixture
async def make_player(tmp_path: Path):
    created: list[GuildPlayer] = []

    def factory(
        *,
        max_queue: int = 50,
        default_volume: float = 1.0,
        with_channel: bool = False,
        queue_file: Path | None = None,
    ) -> GuildPlayer:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        target = queue_file or (tmp_path / f"{len(created)}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        player = _build_player(
            loop,
            target,
            max_queue=max_queue,
            default_volume=default_volume,
            with_channel=with_channel,
        )
        created.append(player)
        return player

    yield factory

    for player in created:
        player._stopping = True
        player._session += 1
        if player.voice.is_playing():
            player.voice.stop()
        pending = [
            task
            for task in (player._advance_task, player._idle_task, player._mix_task)
            if task is not None and not task.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            with contextlib.suppress(Exception):
                await asyncio.gather(*pending, return_exceptions=True)
