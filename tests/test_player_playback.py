from __future__ import annotations

import asyncio

import discord
import pytest

from bot.music.player import MAX_VOLUME, VOLUME_GAIN
from conftest import FakeAudioSource, await_until, make_track


class RecordingFFmpeg(discord.AudioSource):
    instances: list["RecordingFFmpeg"] = []

    def __init__(self, source: str, *, before_options: str | None = None, options: str | None = None) -> None:
        self.source = source
        self.before_options = before_options
        self.options = options
        RecordingFFmpeg.instances.append(self)

    def read(self) -> bytes:
        return b""

    def is_opus(self) -> bool:
        return False


async def test_advance_starts_ffmpeg_with_volume_gain(make_player) -> None:
    p = make_player()
    await p.enqueue([make_track("A"), make_track("B")])
    assert await await_until(lambda: p.current is not None and p.current.title == "A")

    assert p.voice.started == ["FFmpegPCMAudio"]
    assert isinstance(p.voice.source, discord.PCMVolumeTransformer)
    assert type(p.voice.source.original).__name__ == "FFmpegPCMAudio"
    assert p.voice.source.volume == VOLUME_GAIN


@pytest.mark.parametrize(
    ("requested", "expected_volume"),
    [
        (0.5, 0.5),
        (1.0, 1.0),
        (1.5, 1.5),
        (9.0, MAX_VOLUME),
        (-1.0, 0.0),
    ],
)
def test_set_volume_maps_and_clamps(make_player, requested: float, expected_volume: float) -> None:
    p = make_player()
    p.current = make_track("A")
    p.voice.source = discord.PCMVolumeTransformer(FakeAudioSource(), volume=VOLUME_GAIN)
    p.voice.playing = True

    applied = p.set_volume(requested)
    assert applied == expected_volume
    assert p.volume == expected_volume
    assert p.voice.source.volume == expected_volume * VOLUME_GAIN


async def test_clock_freezes_while_paused(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    p._reset_clock()
    await asyncio.sleep(0.05)

    p.voice.pause()
    p._pause_clock()
    frozen = p.position
    await asyncio.sleep(0.1)
    assert abs(p.position - frozen) < 0.01

    p.voice.resume()
    p._resume_clock()
    await asyncio.sleep(0.05)
    assert p.position > frozen


async def test_seek_restarts_stream_with_ss_flag(make_player, monkeypatch: pytest.MonkeyPatch) -> None:
    RecordingFFmpeg.instances = []
    monkeypatch.setattr(discord, "FFmpegPCMAudio", RecordingFFmpeg)

    p = make_player()
    await p.enqueue([make_track("A")])
    assert await await_until(lambda: p.current is not None and p.voice.is_playing())

    applied = p.request_seek(30.0)
    assert applied == 30.0

    assert await await_until(
        lambda: any("-ss 30" in (i.before_options or "") for i in RecordingFFmpeg.instances)
    )
    assert 29.0 < p.position < 32.0
