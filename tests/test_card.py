from __future__ import annotations

import pytest

from bot.music.card import (
    PlayerCardView,
    format_seconds,
    render_card,
    render_tombstone,
)
from conftest import make_track


def test_render_now_shows_progress_requester_and_volume(make_player) -> None:
    p = make_player()
    track = make_track("A")
    track.requester = "Kirill"
    p.current = track

    embed = render_card(p)
    assert embed.title.startswith("🎶 A")
    assert "💠" in embed.description
    assert "Kirill" in embed.description
    assert "Volume 100%" in embed.footer.text


def test_render_queue_page(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    p.queue.append(make_track("B"))
    p.page = "queue"

    embed = render_card(p)
    assert "Queue" in embed.title


def test_render_queue_page_respects_field_limit(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    long_title = "L" * 60
    for i in range(50):
        t = make_track(f"{long_title}{i}")
        t.requester = "VeryLongRequesterName"
        p.queue.append(t)
    p.page = "queue"

    embed = render_card(p)
    for field in embed.fields:
        assert len(field.value) <= 1024
    assert "next page" in embed.fields[0].value


def test_render_history_page(make_player) -> None:
    p = make_player()
    p.current = make_track("B")
    p.history.append(make_track("A"))
    p.page = "history"

    embed = render_card(p)
    assert "History" in embed.title


def test_render_idle(make_player) -> None:
    p = make_player()
    p.current = None
    p.queue.clear()

    embed = render_card(p)
    assert embed.title.startswith("💤")


def test_card_view_has_16_unique_button_ids(make_player) -> None:
    p = make_player()
    view = PlayerCardView(p.cog, p)
    ids = [child.custom_id for child in view.children]
    assert len(ids) == 16
    assert len(set(ids)) == 16


def test_card_view_sync_disables_seek_without_current(make_player) -> None:
    p = make_player()
    p.current = None
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert view.seek_back.disabled
    assert view.seek_fwd.disabled
    assert view.mix_toggle.disabled


def test_card_view_sync_enables_seek_with_current(make_player) -> None:
    p = make_player()
    p.current = make_track("A")
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert not view.seek_back.disabled
    assert not view.seek_fwd.disabled
    assert not view.mix_toggle.disabled


def test_card_view_sync_reflects_mix_state(make_player) -> None:
    import discord

    p = make_player()
    p.current = make_track("A")
    p.mix_url = "https://mymix"
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert view.mix_toggle.style == discord.ButtonStyle.success


def test_card_view_sync_queue_paging(make_player) -> None:
    p = make_player()
    p.page = "queue"
    for i in range(25):
        p.queue.append(make_track(f"t{i}"))
    p.queue_page = 0
    view = PlayerCardView(p.cog, p)
    view.sync()
    assert view.queue_prev.disabled
    assert not view.queue_next.disabled


def test_render_tombstone(make_player) -> None:
    p = make_player()
    p.tracks_played = 2
    p.listen_seconds = 65
    embed = render_tombstone(p)
    assert "Session ended" in embed.title
    assert "2 tracks" in embed.description


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (3661, "1:01:01"),
        (59, "0:59"),
        (60, "1:00"),
        (0, "0:00"),
        (None, "0:00"),
        (-5, "0:00"),
    ],
)
def test_format_seconds(seconds: float | int | None, expected: str) -> None:
    assert format_seconds(seconds) == expected
