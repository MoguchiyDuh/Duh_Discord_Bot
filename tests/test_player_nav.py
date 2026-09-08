from __future__ import annotations

import asyncio
import json

from bot.music.player import LOOP_MODES
from bot.services.youtube import Track
from conftest import await_until, make_track


def _state(player) -> tuple[str | None, list[str], list[str]]:
    return (
        player.current.title if player.current else None,
        [t.title for t in player.queue],
        [t.title for t in player.history],
    )


async def test_skip_walks_queue_into_history(make_player) -> None:
    p = make_player()
    await p.enqueue([make_track("A"), make_track("B"), make_track("C")])
    assert await await_until(lambda: p.current is not None and p.current.title == "A")
    assert _state(p) == ("A", ["B", "C"], [])

    p.history.append(p.stop_current())
    p.kick()
    assert await await_until(lambda: p.current is not None and p.current.title == "B")
    assert _state(p) == ("B", ["C"], ["A"])

    p.history.append(p.stop_current())
    p.kick()
    assert await await_until(lambda: p.current is not None and p.current.title == "C")
    assert _state(p) == ("C", [], ["A", "B"])


async def test_prev_restores_previous_track(make_player) -> None:
    p = make_player()
    await p.enqueue([make_track("A"), make_track("B"), make_track("C")])
    assert await await_until(lambda: p.current is not None and p.current.title == "A")

    for expected in ("B", "C"):
        p.history.append(p.stop_current())
        p.kick()
        assert await await_until(
            lambda expected=expected: p.current is not None and p.current.title == expected
        )
    assert _state(p) == ("C", [], ["A", "B"])

    assert p.prev().title == "B"
    p.stop_current(record=False)
    p.kick()
    assert await await_until(lambda: p.current is not None and p.current.title == "B")
    assert _state(p) == ("B", ["C"], ["A"])

    assert p.prev().title == "A"
    p.stop_current(record=False)
    p.kick()
    assert await await_until(lambda: p.current is not None and p.current.title == "A")
    assert _state(p) == ("A", ["B", "C"], [])


async def test_loop_queue_requeues_and_alternates(make_player) -> None:
    p = make_player()
    p.loop_mode = "queue"
    p.voice.finish_delay = 0.05
    await p.enqueue([make_track("X"), make_track("Y")])
    assert await await_until(lambda: p.current is not None)

    seen: set[str] = set()
    for _ in range(16):
        if p.current is not None:
            seen.add(p.current.title)
            queued = [t.title for t in p.queue]
            assert p.current.title not in queued
            assert sorted([*queued, p.current.title]) == ["X", "Y"]
        await asyncio.sleep(0.05)
    assert seen == {"X", "Y"}


async def test_drain_schedules_idle(make_player) -> None:
    p = make_player()
    p.voice.finish_delay = 0.05
    await p.enqueue([make_track("A")])
    assert await await_until(lambda: p.current is not None and p.current.title == "A")
    assert await await_until(
        lambda: p.current is None and p._idle_task is not None, timeout=3.0
    )
    assert len(p.queue) == 0


def test_track_dict_roundtrip() -> None:
    track = Track("https://youtu.be/a", "Song A", 100)
    assert Track.from_dict(track.to_dict()) == track


async def test_front_enqueue_and_max_queue_cap(make_player) -> None:
    p = make_player(max_queue=3)
    p.voice.playing = True
    a, b, c = make_track("A"), make_track("B"), make_track("C")

    assert await p.enqueue([a, b]) == 2
    assert list(p.queue) == [a, b]
    assert p._queue_file.exists()

    await p.enqueue([c], front=True)
    assert list(p.queue)[0] == c
    assert len(p.queue) == 3

    await p.enqueue([make_track("D")])
    assert len(p.queue) == 3


async def test_cycle_loop_and_persistence_roundtrip(make_player) -> None:
    p = make_player(max_queue=3)
    p.voice.playing = True
    await p.enqueue([make_track("A"), make_track("B"), make_track("C")])

    assert p.cycle_loop() == "track"
    p.save_queue()
    stored = json.loads(p._queue_file.read_text("utf-8"))
    assert stored["loop"] == "track"
    assert len(stored["queue"]) == 3

    reloaded = make_player(max_queue=3, queue_file=p._queue_file)
    reloaded._load_queue()
    assert [t.title for t in reloaded.queue] == ["A", "B", "C"]
    assert reloaded.loop_mode == "track"


def test_loop_modes_constant() -> None:
    assert LOOP_MODES == ("off", "track", "queue")
