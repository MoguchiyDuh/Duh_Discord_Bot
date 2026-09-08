from __future__ import annotations

from conftest import await_until, make_track


def _drain(player) -> None:
    if player.current is not None:
        player.history.append(player.current)
        player.current = None
        player._session += 1
        if player.voice.is_playing():
            player.voice.stop()
    player.kick()


async def test_mix_pulls_next_batch_on_drain(make_player) -> None:
    p = make_player()
    yt = p.cog.bot.youtube
    batch1 = [make_track("1a"), make_track("1b")]
    yt.batches = [[make_track("2a"), make_track("2b")]]
    p.start_mix("https://mymix", batch1)
    assert p.mix_url == "https://mymix"
    assert p._mix_seen == {"1a", "1b"}

    await p.enqueue(batch1)
    assert await await_until(lambda: p.current is not None and p.current.title == "1a")
    _drain(p)
    assert await await_until(lambda: p.current is not None and p.current.title == "1b")
    _drain(p)
    assert await await_until(lambda: p.current is not None and p.current.title == "2a")
    assert "2b" in [t.title for t in p.queue]
    assert p.mix_url == "https://mymix"


async def test_mix_dedupes_seen_video_ids(make_player) -> None:
    p = make_player()
    yt = p.cog.bot.youtube
    batch1 = [make_track("1a"), make_track("1b")]
    yt.batches = [[make_track("1a"), make_track("1b"), make_track("2a")]]
    p.start_mix("https://mymix", batch1)

    await p.enqueue(batch1)
    assert await await_until(lambda: p.current is not None and p.current.title == "1a")
    _drain(p)
    assert await await_until(lambda: p.current is not None and p.current.title == "1b")
    _drain(p)
    assert await await_until(lambda: p.current is not None and p.current.title == "2a")
    assert p._mix_seen == {"1a", "1b", "2a"}


async def test_mix_yields_to_user_added_tracks(make_player) -> None:
    p = make_player()
    yt = p.cog.bot.youtube
    yt.batches = [[make_track("mix1")]]
    p.start_mix("https://mymix", [make_track("1a")])

    await p.enqueue([make_track("1a")])
    assert await await_until(lambda: p.current is not None and p.current.title == "1a")
    await p.enqueue([make_track("user1")])
    calls_before = yt.playlist_calls
    _drain(p)
    assert await await_until(lambda: p.current is not None and p.current.title == "user1")
    assert yt.playlist_calls == calls_before
    assert p.mix_url == "https://mymix"


async def test_mix_exhausts_after_three_misses(make_player) -> None:
    p = make_player()
    yt = p.cog.bot.youtube
    yt.batches = [[], [], []]
    p.start_mix("https://mymix", [make_track("1a")])

    await p.enqueue([make_track("1a")])
    assert await await_until(lambda: p.current is not None and p.current.title == "1a")
    _drain(p)
    assert await await_until(lambda: p.mix_url is None, timeout=3.0)
    assert p.current is None
    assert len(p.queue) == 0
    assert p._idle_task is not None


async def test_mix_cap_does_not_exhaust_radio(make_player) -> None:
    p = make_player(max_queue=3)
    yt = p.cog.bot.youtube
    yt.batches = [
        [make_track("m1"), make_track("m2"), make_track("m3")],
        [make_track("m4")],
    ]
    p.start_mix("https://mymix", [make_track("1a")])

    await p.enqueue([make_track("1a")])
    assert await await_until(lambda: p.current is not None and p.current.title == "1a")
    _drain(p)
    assert await await_until(
        lambda: p.current is not None and p.current.title == "m1" and len(p.queue) == 2,
        timeout=3.0,
    )
    assert p.mix_url == "https://mymix"

    for t in list(p.queue):
        p.queue.remove(t)
    _drain(p)
    assert await await_until(lambda: p.current is not None and p.current.title == "m4", timeout=3.0)
    assert p.mix_url == "https://mymix"


async def test_stop_mix_prevents_further_fetch(make_player) -> None:
    p = make_player()
    yt = p.cog.bot.youtube
    yt.batches = [[make_track("mix1")]]
    p.start_mix("https://mymix", [make_track("1a")])

    await p.enqueue([make_track("1a")])
    assert await await_until(lambda: p.current is not None and p.current.title == "1a")
    p.stop_mix()
    assert p.mix_url is None
    calls_before = yt.playlist_calls
    _drain(p)
    assert await await_until(lambda: p._idle_task is not None)
    assert p.current is None
    assert len(p.queue) == 0
    assert yt.playlist_calls == calls_before


async def test_toggle_mix_on_and_off(make_player) -> None:
    p = make_player()
    assert p.toggle_mix("Kirill") == "Nothing is playing — start a track first."
    assert p.mix_url is None

    await p.enqueue([make_track("abc")])
    assert await await_until(lambda: p.current is not None and p.current.title == "abc")
    assert p.mix_url is None

    assert p.toggle_mix("Kirill") is None
    assert p.mix_url == "https://www.youtube.com/watch?v=abc&list=RDabc"

    assert p.toggle_mix("Kirill") is None
    assert p.mix_url is None
